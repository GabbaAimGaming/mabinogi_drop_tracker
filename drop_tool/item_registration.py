"""通常の品名修正と、上限付きの画像見本登録。元の観測は保持する。"""
import copy
from . import learning
from .names import normalize
from .item_links import name_key, resolve_name


def assign(catalog, source, target, kind, *, new=False, run_id=None, row_index=None, image=None):
    if kind not in ('material', 'excluded', 'review'):
        raise ValueError('集計・除外・未確認を選んでください。')
    target = normalize(target)
    if not target or len(target) > 160 or target == '読取不明':
        raise ValueError('正式な品名を160文字以内で入力してください。')
    existing = catalog.find(target)
    if new and existing:
        raise ValueError('登録済みの品名です。辞書候補から選択してください。')
    if not new and existing is None:
        raise ValueError('辞書候補から正式名を選んでください。新しい品は新規登録を使ってください。')
    target = existing['name'] if existing else target
    store = catalog.store
    if name_key(target) in store.data.get('item_links', {}):
        raise ValueError('別の品への対応付けがある名前です。集計先の正式名を選んでください。')
    source = normalize(source)
    previous = copy.deepcopy(store.data)
    created = None
    try:
        names = store.data.setdefault('item_names', [])
        for name in (source, target):
            if name and name != '読取不明' and name not in names:
                names.append(name)
        # 正式名側も指定の扱いにする。数量付きの旧指定が残る矛盾も解消する。
        for name in list(store.data['overrides']):
            if name_key(name) == name_key(target):
                store.data['overrides'][name] = kind
        store.data['overrides'][normalize(target)] = kind
        if source and source != '読取不明' and name_key(source) != name_key(target):
            store.data.setdefault('item_links', {})[name_key(source)] = target
            resolve_name(store.data, source)  # 壊れた既存データや循環を保存前に検出する。
        if run_id is not None:
            run = store.find(run_id)
            row = run['rows'][row_index]
            # 「読取不明」は別アイテムにも使われるため、全履歴への対応付けは禁止。
            if not source or source == '読取不明' or (name_key(source) == name_key(target) and row['name'] != target):
                row['resolved_name'] = target
            row['reviewed_kind'] = kind
            if run['status'] == 'confirmed':
                run['status'] = 'review'
        # 分割した行が同じ結合画像を共有している場合、単品の見本にはしない。
        shared_image = (run_id is not None and row.get('image') and
                        sum(r.get('image') == row['image'] for r in run['rows']) > 1)
        if image is not None and not shared_image:
            try:
                created = learning.add(store, target, kind, image)
            except OSError:
                pass  # 見本を書けなくても、利用者の通常の品名修正は保存する。
        store.save()
    except Exception:
        store.data = previous
        if created:
            try:
                created.unlink(missing_ok=True)
            except OSError:
                pass  # 書き込み途中の孤立見本は次回の整理で回収する。
        raise
    learning.cleanup(store, previous['templates'])
    catalog.__init__(store)


def unlink(catalog, names):
    """対応付けだけを解除する。登録名・原記録・学習画像を削除しない。"""
    previous = copy.deepcopy(catalog.store.data)
    try:
        for name in names:
            catalog.store.data.get('item_links', {}).pop(name_key(name), None)
        catalog.store.save()
    except Exception:
        catalog.store.data = previous
        raise
    catalog.__init__(catalog.store)
