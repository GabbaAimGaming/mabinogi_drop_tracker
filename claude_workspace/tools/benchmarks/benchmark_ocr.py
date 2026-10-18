"""同梱モデルを提供済み切り抜きで再評価する。画像の送信やデータ変更はしない。"""
import json
from pathlib import Path
import sys
import time
import unicodedata
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from drop_tool.ocr_engine import engine


def normalize(text):
    return ''.join(unicodedata.normalize('NFKC', text).split()).replace('スクロール-', 'スクロール・')


def main():
    corpus = json.loads((HERE / 'corpus.json').read_text('utf-8'))
    recognizer = engine()
    images = [Image.open(HERE / 'crops' / row['file']).convert('RGB') for row in corpus]
    started = time.perf_counter()
    results = recognizer.recognize(images)
    seconds = time.perf_counter() - started
    hits = 0
    total = 0
    for row, (text, confidence) in zip(corpus, results):
        if row['score_item']:
            total += 1
            hits += normalize(text) == normalize(row['expected'])
        print(row['file'], text, f'{confidence:.3f}')
    print(f'一致 {hits}/{total}、39枚の推論 {seconds:.2f}秒（モデル読込・撮影・検出を除く）')


if __name__ == '__main__':
    main()
