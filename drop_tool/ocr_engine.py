"""Windows OCRとの通信。品名検出や保存からプロセス実行を分離する。"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from .config import ROOT


def invoke(arguments):
    executable = shutil.which('powershell.exe')
    if executable is None:
        raise RuntimeError('Windows PowerShell（powershell.exe）が見つかりません。')
    try:
        proc = subprocess.run(
            [executable, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
             '-File', str(ROOT / 'ocr_ja.ps1'), *arguments],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=35)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('Windows OCRが35秒以内に応答しませんでした。') from exc
    if proc.returncode:
        detail = proc.stderr.decode('utf-8-sig', errors='replace').strip()
        raise RuntimeError('Windows OCR：' + (detail[:1200] or '処理に失敗しました。'))
    try:
        return json.loads(proc.stdout.decode('utf-8-sig'))
    except (UnicodeError, ValueError) as exc:
        raise RuntimeError('Windows OCRから有効な結果を受け取れませんでした。') from exc


def probe():
    """言語エンジンの生成を確認。実スクリーンショットの認識成功は保証しない。"""
    return invoke(['-Probe'])


def make_atlas(images):
    """切り抜きが隣の行へはみ出さない高さで並べる。最大10件ずつ呼ぶ。"""
    from PIL import Image
    row_height = max(100, max(im.height for im in images) * 3 + 20)
    width = max(im.width for im in images) * 3 + 20
    if width > 2000 or row_height * len(images) > 2000:
        raise ValueError('OCR用の画像が大きすぎます。品名の切り抜きを確認してください。')
    atlas = Image.new('RGB', (width, row_height * len(images)), 'black')
    for index, im in enumerate(images):
        # 二値化で細い画線を落とさず、撮影時の色と濃淡をOCRへ渡す。
        enlarged = im.convert('RGB').resize((im.width * 3, im.height * 3), Image.Resampling.LANCZOS)
        atlas.paste(enlarged, (10, index * row_height + 10))
    return atlas, row_height


def suggestions(images):
    """大量の品名でも一枚の巨大画像にせず、元の順序でOCR候補を返す。"""
    from .tracker import normalize
    found = []
    for start in range(0, len(images), 10):
        batch = images[start:start + 10]
        atlas, row_height = make_atlas(batch)
        with tempfile.TemporaryDirectory(prefix='mabi-ocr-') as temp:
            path = Path(temp) / 'labels.png'
            atlas.save(path)
            lines = invoke(['-ImagePath', str(path)])
        if isinstance(lines, dict):
            lines = [lines]
        if not isinstance(lines, list):
            raise ValueError('OCRの行データが不正です。')
        names = [''] * len(batch)
        for line in lines:
            words = line.get('words', [])
            if not words:
                continue
            index = int(min(w['y'] for w in words) // row_height)
            if 0 <= index < len(names):
                names[index] += normalize(line['text'])
        found.extend(names)
    return found
