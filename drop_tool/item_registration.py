"""登録・対応付け・任意の見本追加を一度の保存で確定する。元の観測と見本は保持。"""
import copy
import hashlib
from .tracker import normalize
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
        if image is not None:
            learned_name = source if source and source != '読取不明' else target
            digest = hashlib.sha256(image.tobytes() + str(image.size).encode() + learned_name.encode('utf-8')).hexdigest()[:24]
            folder = store.folder / 'labels'
            folder.mkdir(exist_ok=True)
            file = folder / (digest + '.png')
            image.save(file)
            record = {'name':learned_name, 'kind':kind, 'path':file.relative_to(store.folder).as_posix()}
            # 元の見本は消さない。同じ見本の繰返し登録だけ増殖を防ぐ。
            if not any(t['path'] == record['path'] for t in store.data['templates']):
                store.data['templates'].append(record)
        store.save()
    except Exception:
        store.data = previous
        raise
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
