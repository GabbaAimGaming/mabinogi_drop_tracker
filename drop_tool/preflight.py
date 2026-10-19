"""同梱資産・ライブラリ・推論を確認する環境診断。記録の読込み・書換えは行わない。"""
import importlib.metadata
import json
import platform
import sys
import tempfile
from .config import ROOT


def check_assets(root):
    """認識器が起動時に要求する全画像と設定を確認する。"""
    manifest = root / 'references/labels.json'
    records = json.loads(manifest.read_text('utf-8'))
    for record in records:
        if not (root / record['path']).is_file():
            raise ValueError('参照画像がありません：' + record['path'])
    rules = json.loads((root / 'exclusions.json').read_text('utf-8'))
    for key in ('exclude_exact', 'exclude_prefix', 'equipment_suffixes', 'confirmed_materials'):
        value = rules.get(key)
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise ValueError('exclusions.jsonの項目が不正です：' + key)
    master = json.loads((root / 'item-master.json').read_text('utf-8'))
    if master.get('schema_version') != 1 or not isinstance(master.get('items'), list):
        raise ValueError('item-master.jsonの形式が不正です。')
    for sound in ('read-complete.wav', 'capture-complete.wav', 'read-error.wav'):
        if not (root / 'assets' / sound).is_file():
            raise ValueError('効果音がありません：assets/' + sound)
    if not (root / 'assets/karen.png').is_file():
        raise ValueError('カレンの画像がありません：assets/karen.png')
    from .ocr_engine import check_model
    check_model(root)
    chest_folder = root / 'assets/chests'
    for name in ('question.png', 'buttons.png'):
        if not (root / 'assets/near-dialog' / name).is_file():
            raise ValueError('ネアル画面の参照データがありません：' + name)
    chest_manifest = json.loads((chest_folder / 'manifest.json').read_text('utf-8'))
    for template in chest_manifest['templates']:
        if not (chest_folder / template['file']).is_file():
            raise ValueError('宝箱の参照データがありません：' + template['file'])
    if not (root/'assets/chest-shape.npz').is_file():
        raise ValueError('宝箱の輪郭データがありません。')
    fragments=root/'assets/chest-fragments'
    for entry in json.loads((fragments/'manifest.json').read_text('utf-8'))['templates']:
        if not (fragments/entry['file']).is_file():
            raise ValueError('宝箱の部分見本がありません：'+entry['file'])
    parts=root/'assets/chest-parts'
    for entry in json.loads((parts/'manifest.json').read_text('utf-8'))['templates']:
        if not (parts/entry['file']).is_file():
            raise ValueError('宝箱の部分照合データがありません：'+entry['file'])


def check_tk():
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    root.destroy()


def check_libraries():
    for line in (ROOT / 'requirements.txt').read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        name, expected = line.split('==')
        actual = importlib.metadata.version(name)
        if actual != expected:
            raise ValueError(f'{name}：必要 {expected} / 現在 {actual}')
    # DLLの読込失敗もここで検出する。
    import PIL, cv2, numpy  # noqa: F401


def check_writable():
    # 設定保存に必要な場所へ一時ファイルを作る。利用者のファイルを変更しない。
    with tempfile.TemporaryFile(dir=ROOT):
        pass
    folder = ROOT / 'data'
    if folder.exists():
        with tempfile.TemporaryFile(dir=folder):
            pass


def check_ocr():
    from .ocr_engine import probe
    probe()


def inspect():
    checks = [
        ('同梱ファイルと除外設定', lambda: check_assets(ROOT), True),
        ('保存先への書込み', check_writable, True),
        ('画面機能（Tk）', check_tk, True),
        ('画像ライブラリ', check_libraries, True),
        ('同梱日本語OCR（CPU）', check_ocr, False),
    ]
    lines = ['ドロップ記録 v1.1.2 環境診断', 'OS：' + platform.platform(),
             'Python：' + sys.version.split()[0]]
    fatal = False
    for name, action, required in checks:
        try:
            action()
            lines.append('OK：' + name)
        except Exception as exc:
            lines.append(('停止：' if required else '注意：') + name + ' — ' + str(exc))
            fatal |= required
    lines.append('OCRが使えない場合も、学習済み見本の照合と手動の名前登録は利用できます。')
    return lines, fatal


def main():
    lines, fatal = inspect()
    text = '\n'.join(lines)
    print(text)
    try:
        (ROOT / '環境診断.txt').write_text(text, 'utf-8')
    except OSError:
        print('診断ファイルを保存できません。上の表示を確認してください。')
    return int(fatal)


if __name__ == '__main__':
    sys.exit(main())
