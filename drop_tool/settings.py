"""利用者設定（data/settings.json）。壊れた値は既定値に戻し、起動を止めない。"""
import json
from pathlib import Path

FILE = 'settings.json'
KEEP_RANGE = (1, 1000)
SCAN_MODES = ('full', 'center')

DEFAULTS = {
    # 品名画像（data/evidence）の自動削除
    'evidence_auto_delete': True,
    'evidence_keep_runs': 3,
    # 選んだウィンドウだけを Windows Graphics Capture で撮影する
    'window_share': False,
    # 箱の探索は常に全体。full / center は品名の解析範囲を選ぶ。
    'scan_mode': 'full',
    'auto_reward': True,
    'update_url': '',
}


def _valid(key, value):
    if key == 'update_url':
        return isinstance(value, str) and len(value) <= 2048
    if key in ('evidence_auto_delete', 'window_share', 'auto_reward'):
        return isinstance(value, bool)
    if key == 'evidence_keep_runs':
        return type(value) is int and KEEP_RANGE[0] <= value <= KEEP_RANGE[1]
    if key == 'scan_mode':
        return value in SCAN_MODES
    return False


def load(folder):
    settings = dict(DEFAULTS)
    try:
        saved = json.loads((Path(folder) / FILE).read_text('utf-8'))
    except (OSError, ValueError):
        return settings
    if isinstance(saved, dict):
        for key in DEFAULTS:
            if key in saved and _valid(key, saved[key]):
                settings[key] = saved[key]
    return settings


def save(folder, **changes):
    """指定した項目だけを検証して書き換える。未知の既存キーは残す。"""
    for key, value in changes.items():
        if key not in DEFAULTS:
            raise ValueError(f'不明な設定です：{key}')
        if not _valid(key, value):
            if key == 'evidence_keep_runs':
                raise ValueError(f'画像を残す世代数は{KEEP_RANGE[0]}～{KEEP_RANGE[1]}の整数で指定してください。')
            raise ValueError(f'設定値が不正です：{key}')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / FILE
    try:
        current = json.loads(path.read_text('utf-8'))
        if not isinstance(current, dict):
            current = {}
    except (OSError, ValueError):
        current = {}
    current.update(changes)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2), 'utf-8')
    temporary.replace(path)
    return load(folder)
