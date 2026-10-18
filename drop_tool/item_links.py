"""元の観測名を残し、明示された対応付けだけを集計時に解決する。"""
import re
import unicodedata


def name_key(name):
    key = ''.join(unicodedata.normalize('NFKC', name).split())
    key = re.sub(r'\([\d,]+\)$', '', key)
    return re.sub(r'^(専用)?エンチャントスクロール-', lambda m: (m[1] or '') + 'エンチャントスクロール・', key)


def resolve_name(data, name):
    links = data.get('item_links', {})
    if not isinstance(links, dict):
        raise ValueError('品名の対応付けの保存形式が不正です。')
    seen = set()
    while name_key(name) in links:
        key = name_key(name)
        if key in seen:
            raise ValueError('品名の対応付けが循環しています。')
        seen.add(key)
        name = links[key]
        if not isinstance(name, str) or not name.strip():
            raise ValueError('集計先の品名が不正です。')
    return name


def row_identity(data, row):
    """行単独の確認と名前の対応付けを解決。確定済み周回の集合計算にも共用する。"""
    original = row.get('resolved_name', row['name'])
    target = resolve_name(data, original)
    if name_key(original) in data.get('item_links', {}):
        # 明示した誤登録名だけは、集計先の扱いを使用する。元行は変更しない。
        return target, data.get('overrides', {}).get(''.join(unicodedata.normalize('NFKC', target).split()), 'review')
    return original, row.get('reviewed_kind', row['kind'])
