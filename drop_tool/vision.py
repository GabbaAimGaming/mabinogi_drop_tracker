"""画面の品名切り抜き、見本照合、日本語OCRの候補生成。"""
import hashlib
import json
import subprocess
import cv2
import numpy as np
from PIL import Image
from .tracker import ROOT, Rules, normalize
from .label_images import split_labels
from .ocr_engine import suggestions

def ink(image):
    a = np.asarray(image.convert('RGB')).astype(float)
    m = (a.min(2) > 175) | (a[:, :, 1] > 120) & (a[:, :, 1] > a[:, :, 0] * 1.5) & (a[:, :, 1] > a[:, :, 2] * 1.4)
    ys, xs = np.where(m)
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype('uint8') if len(xs) else None

def similarity(a, b):
    a = ink(a)
    b = ink(b)
    if a is None or b is None:
        return 0.0
    if abs(a.shape[1] / a.shape[0] - b.shape[1] / b.shape[0]) > 0.25:
        return 0.0
    b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_NEAREST)
    return float(np.logical_and(a, b).sum() / max(1, np.logical_or(a, b).sum()))

class Vision:
    """ALT品名の切り抜き・見本照合・未登録名のOCR候補を担当する。"""

    def __init__(self, store):
        self.store = store
        self.cache = {}
        self.reload()

    def reload(self):
        self.rules = Rules(self.store.data['overrides'])
        self.templates = []
        self.cache = {}
        for record in json.loads((ROOT / 'references/labels.json').read_text('utf-8')):
            kind = self.store.data['overrides'].get(record['name'], record['kind'])
            self.templates.append((record['name'], kind, Image.open(ROOT / record['path']).convert('RGB')))
        for record in self.store.data['templates']:
            path = self.store.folder / record['path']
            if path.exists():
                learned = Image.open(path).convert('RGB')
                self.templates = [t for t in self.templates if similarity(learned, t[2]) < 0.98]
                self.templates.append((record['name'], self.store.data['overrides'].get(record['name'], record['kind']), learned))
    def boxes(self, image):
        """中央領域の白/緑文字と黒い縁から品名を探す。箱認識は不要。"""
        x0, y0 = (round(image.width * 0.22), round(image.height * 0.12))
        x1, y1 = (round(image.width * 0.8), round(image.height * 0.82))
        region = image.crop((x0, y0, x1, y1))
        a = np.asarray(region).astype(float)
        m = ((a.min(2) > 175) | (a[:, :, 1] > 120) & (a[:, :, 1] > a[:, :, 0] * 1.5) & (a[:, :, 1] > a[:, :, 2] * 1.4)).astype('uint8') * 255
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((1, 13), 'uint8'))
        _, _, stats, _ = cv2.connectedComponentsWithStats(m)
        boxes = []
        for x, y, w, h, area in stats[1:]:
            if not (7 <= h <= 18 and 25 <= w <= 550 and (x >= 2) and (y >= 2) and (x + w + 2 <= region.width) and (y + h + 2 <= region.height)):
                continue
            patch = a[y - 2:y + h + 2, x - 2:x + w + 2]
            edge = np.concatenate((patch[:2].reshape(-1, 3), patch[-2:].reshape(-1, 3)))
            if np.mean(edge.max(1) < 70) < 0.72:
                continue
            boxes.append((y, x, region.crop((x - 2, y - 2, x + w + 2, y + h + 2))))
        from .label_detection import recover_rows
        # 従来の確実な枠を優先し、周囲の発光で落ちた行を補う。
        for x, y, w, h in recover_rows(region):
            if any(abs(y - old_y) <= 3 and x < old_x + old_im.width and x + w > old_x
                   for old_y, old_x, old_im in boxes):
                continue
            boxes.append((y, x, region.crop((max(0,x-2), max(0,y-2),
                                             min(region.width,x+w+2), min(region.height,y+h+2)))))
        return [piece for _, _, im in sorted(boxes) for piece in split_labels(im)
                if np.mean(np.asarray(piece).max(2) < 90) >= .20]

    def recognize_template(self, image):
        """確認済み画像との一致と次点との差を検証する。曖昧ならOCRへ回す。"""
        scores = sorted([(similarity(image, t), n, k) for n, k, t in self.templates], reverse=True)
        if not scores or scores[0][0] < 0.92:
            return None
        score, name, kind = scores[0]
        second = next((s for s, n, k in scores[1:] if (n, k) != (name, kind)), 0.0)
        if score - second < 0.035:
            return None
        return (name, self.store.data['overrides'].get(name, kind))

    def ocr_suggestions(self, images):
        """Windowsとの通信を専用モジュールへ委譲。既存のテスト・拡張用入口は保持。"""
        return suggestions(images)

    def analyze(self, image):
        """見本を優先し、未登録名のOCRは候補扱いにする。手動確認の必要性を保持する。"""
        image = image.convert('RGB')
        images = self.boxes(image)
        labels = []
        unknown = []
        for im in images:
            m = ink(im)
            key = hashlib.sha256(m.tobytes() + str(m.shape).encode()).hexdigest() if m is not None else ''
            known = self.recognize_template(im)
            if known:
                name, kind = known
                raw = name
            elif key in self.cache:
                name, kind, raw = self.cache[key]
            else:
                name = ''
                kind = 'review'
                raw = ''
                unknown.append((len(labels), im, key))
            labels.append({'name': name, 'kind': kind, 'raw': raw, 'image': im, 'fingerprint': key})
        ocr_error = ''
        if unknown:
            try:
                suggestions = self.ocr_suggestions([im for _, im, _ in unknown])
            except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as exc:
                suggestions = [''] * len(unknown)
                ocr_error = str(exc)
            for (i, im, key), raw in zip(unknown, suggestions):
                kind = 'excluded' if self.rules.classify(raw) == 'excluded' else 'review'
                labels[i].update(name=raw or '読取不明', kind=kind, raw=raw)
                if not ocr_error:
                    self.cache[key] = (labels[i]['name'], kind, raw)
            if len(self.cache) > 200:
                self.cache.clear()
        labels = [label for label in labels if normalize(label['raw']).lower() not in ('ctrl+f', 'ctrl+fキー')]
        message = 'ALTの品名が見つかりません。' if not labels else f'{len(labels)}行を検出'
        if ocr_error:
            message += ' / OCRエラー：' + ocr_error
        return {'labels': labels, 'message': message}

    def learn(self, name, kind, image):
        """品名画像と集計/除外の指定を保存する。同じ見た目の誤った関連付けを置き換える。"""
        name = normalize(name)
        if not name or kind not in ('material', 'excluded'):
            raise ValueError('商品名と集計/除外を指定してください。')
        folder = self.store.folder / 'labels'
        folder.mkdir(exist_ok=True)
        digest = hashlib.sha256(image.tobytes() + name.encode('utf-8')).hexdigest()[:20]
        path = folder / (digest + '.png')
        image.save(path)
        rel = path.relative_to(self.store.folder).as_posix()
        self.store.data['templates'] = [r for r in self.store.data['templates'] if r['path'] != rel]
        self.store.data['templates'].append({'name': name, 'kind': kind, 'path': rel})
        self.store.data['overrides'][name] = kind
        self.store.save()
        self.reload()

