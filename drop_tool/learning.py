"""修正時の品名画像を上限付きで保持する。認識結果だけでは学習しない。"""
import hashlib
import io
import re

from .item_links import name_key, resolve_name

PER_ITEM = 3
MAX_SAMPLES = 1000
MAX_BYTES = 16 * 1024 * 1024
MAX_IMAGE_BYTES = 128 * 1024


def owned_path(store, relative):
    """学習処理が生成した切り抜きだけを整理対象にする。"""
    if not isinstance(relative, str) or not re.fullmatch(
            r'labels/(?:auto-[a-f0-9]{24}|[a-f0-9]{20,24})\.png', relative):
        return None
    path = store.folder / relative
    if path.is_symlink() or (store.folder / 'labels').is_symlink():
        return None
    if path.resolve().parent != (store.folder.resolve() / 'labels'):
        return None
    return path


def eligible(image):
    """単一行の品名切り抜きだけ。結合・全画面・文字のない画像は覚えない。"""
    from .label_images import split_labels, text_pixels
    if image.width > 1536 or image.height > 192 or image.width * image.height > 200000:
        return False
    mask = text_pixels(image, include_red=True, include_cyan=True, include_purple=True)
    if mask.sum() < 12 or mask.mean() > .8 or len(split_labels(image)) != 1:
        return False
    rows = mask.any(axis=1).nonzero()[0]
    columns = mask.any(axis=0).nonzero()[0]
    if not len(rows) or len(columns) < 8 or columns[-1] - columns[0] + 1 < (rows[-1] - rows[0] + 1) * 1.6:
        return False  # アイコンなど正方形に近い図柄を、品名の見本として覚えない。
    # 上下に分かれた文字列は単一品として登録しない。
    return bool(len(rows)) and not any(b - a > 3 for a, b in zip(rows, rows[1:]))


def bounded(store, records):
    """新しい見本を優先し、品ごと・全体件数・画像容量の全上限を守る。"""
    selected, counts, paths, total = [], {}, set(), 0
    for record in reversed(records):
        path = owned_path(store, record.get('path'))
        if path is None or not path.is_file():
            continue
        key = name_key(resolve_name(store.data, record['name']))
        try:
            size = path.stat().st_size
        except OSError:
            continue  # 利用者が見本を整理中でも、残った見本で続ける。
        if (record['path'] in paths or counts.get(key, 0) >= PER_ITEM
                or len(selected) >= MAX_SAMPLES or total + size > MAX_BYTES):
            continue
        selected.append(record); paths.add(record['path'])
        counts[key] = counts.get(key, 0) + 1; total += size
    return list(reversed(selected))


def add(store, name, kind, image):
    """保存前の見本一覧を更新し、新規ファイルを返す。JSON失敗時はcallerが戻す。"""
    from .vision import ink, load_mask, mask_similarity
    if kind not in ('material', 'excluded') or not eligible(image):
        return None
    image = image.convert('RGB')
    buffer = io.BytesIO(); image.save(buffer, format='PNG')
    raw = buffer.getvalue()
    if len(raw) > MAX_IMAGE_BYTES:
        return None
    fingerprint = hashlib.sha256(raw + name.encode('utf-8')).hexdigest()[:24]
    relative = 'labels/auto-' + fingerprint + '.png'
    path = owned_path(store, relative)
    if path is None:
        return None
    path.parent.mkdir(exist_ok=True)
    created = None
    if not path.exists():
        # 既存の見本を上書きせず、保存失敗で半端な画像も残さない。
        try:
            with path.open('xb') as stream:
                stream.write(raw)
            created = path
        except OSError:
            path.unlink(missing_ok=True)
            raise
    try:
        mask = ink(image); records = []
        for record in store.data['templates']:
            old = owned_path(store, record.get('path'))
            if old is None or not old.is_file():
                continue
            try:
                duplicate = mask_similarity(mask, load_mask(old)) >= .98
            except (OSError, ValueError):
                duplicate = False
            if not duplicate:
                records.append(record)
        records.append({'name': name, 'kind': kind, 'path': relative})
        store.data['templates'] = bounded(store, records)
    except Exception:
        if created:
            created.unlink(missing_ok=True)
        raise
    return created


def cleanup(store, previous=()):
    """JSON保存成功後だけ、参照されなくなった自動生成画像を消す。"""
    live = {r['path'] for r in store.data['templates']}
    candidates = {r.get('path') for r in previous}
    folder = store.folder / 'labels'
    if folder.is_dir() and not folder.is_symlink():
        # 旧版もハッシュ名で生成していた。参照を失った旧見本も回収する。
        candidates.update('labels/' + p.name for p in folder.glob('*.png'))
    for relative in candidates - live:
        path = owned_path(store, relative)
        if path:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass  # ロックされた画像は次の整理で再試行する。


def maintain(store):
    """旧版の見本も起動時に自動整理。見本以外の証拠画像・履歴には触れない。"""
    previous = store.data['templates']
    current = bounded(store, previous)
    if current != previous:
        store.data['templates'] = current
        try:
            store.save()
        except Exception:
            store.data['templates'] = previous
            raise
    cleanup(store, previous)
