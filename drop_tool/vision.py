"""画面の品名切り抜き、見本照合、日本語OCRの候補生成。"""
import copy
import hashlib
import json
import cv2
import numpy as np
from PIL import Image
from .tracker import ROOT, Rules, normalize
from .label_images import split_labels, text_pixels
from .label_detection import recover_rows, merge_fragments
from .hud_filter import remove_gauge_candidates
from . import alt_display
from .ocr_engine import suggestions
from .item_catalog import ItemCatalog
from .hud_text import is_hud_text,is_system_notice

def ink(image):
    """見本照合用の文字マスク。OCRに渡すカラー画像とは別に扱う。"""
    m = text_pixels(image,include_red=True)
    ys, xs = np.where(m)
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype('uint8') if len(xs) else None

def similarity(a, b):
    """文字の縦横比が近い見本だけ、重なる画素の割合で比較する。"""
    return mask_similarity(ink(a), ink(b))


def mask_similarity(a, b):
    """作成済みの文字マスク同士の比較。見本側のマスクを毎フレーム作り直さない。"""
    if a is None or b is None:
        return 0.0
    if abs(a.shape[1] / a.shape[0] - b.shape[1] / b.shape[0]) > 0.25:
        return 0.0
    b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_NEAREST)
    return float(np.logical_and(a, b).sum() / max(1, np.logical_or(a, b).sum()))


def load_mask(path):
    """画像を開いたままにせず、照合用マスクだけを保持する。"""
    with Image.open(path) as source:
        return ink(source.convert('RGB'))


# 報酬の品名表示を探す範囲（画面に対する比率）。中央スキャンの撮影範囲と共通。
# 品が多いとALTの品名板が縦に長く積み上がるため、下側を0.82→0.88へ広げた。
# 上端は画面上部のタイマー等（黒地の白文字が縦に並ぶ）を拾うため0.12のまま。
CENTER = (0.22, 0.12, 0.8, 0.88)


def label_presence(region):
    """ALTの品名板の列がありそうなら1、なければ0（alt_display.quick_checkの結果）。"""
    return int(alt_display.quick_check(region))


class Vision:
    """ALT品名の切り抜き・見本照合・未登録名のOCR候補を担当する。"""

    def __init__(self, store):
        self.store = store
        self.cache = {}
        # 見本画像はパスごとに内容が固定（学習画像は内容ハッシュ名）なので、
        # マスクを使い回して再読込の度にPNGを開き直さない。
        self.mask_cache = {}
        self.reload()

    def _mask(self, path):
        key = str(path)
        if key not in self.mask_cache:
            self.mask_cache[key] = load_mask(path)
        return self.mask_cache[key]

    def reload(self):
        """見本は(品名, 扱い, 文字マスク)で保持する。画像本体はメモリーに残さない。"""
        self.rules = Rules(self.store.data['overrides'])
        self.catalog = ItemCatalog(self.store)
        self.templates = []
        self.cache = {}
        overrides = self.store.data['overrides']
        for record in json.loads((ROOT / 'references/labels.json').read_text('utf-8')):
            kind = overrides.get(record['name'], record['kind'])
            self.templates.append((record['name'], kind, self._mask(ROOT / record['path'])))
        live = set()
        for record in self.store.data['templates']:
            path = self.store.folder / record['path']
            if not path.exists():
                continue
            live.add(str(path))
            learned = self._mask(path)
            # 後から学習したほぼ同一の見本を優先する（従来どおり）。
            self.templates = [t for t in self.templates if mask_similarity(learned, t[2]) < 0.98]
            self.templates.append((record['name'], overrides.get(record['name'], record['kind']), learned))
        builtin = {str(ROOT / r['path']) for r in json.loads((ROOT / 'references/labels.json').read_text('utf-8'))}
        self.mask_cache = {k: v for k, v in self.mask_cache.items() if k in live or k in builtin}

    def boxes(self, image, cropped=False):
        """中央領域の白/緑文字と黒い縁から品名を探す。箱認識は不要。

        cropped=Trueは、中央スキャンで既にCENTERの範囲だけを撮影した画像。
        """
        if cropped:
            region = image
        else:
            x0, y0 = (round(image.width * CENTER[0]), round(image.height * CENTER[1]))
            x1, y1 = (round(image.width * CENTER[2]), round(image.height * CENTER[3]))
            region = image.crop((x0, y0, x1, y1))
        from .label_scale import normalized
        original_region = region
        region, recognition_scale = normalized(region)
        a = np.asarray(region).astype(float)
        m = text_pixels(region).astype('uint8') * 255
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
        # 従来の確実な枠を優先し、周囲の発光で落ちた行を補う。
        for x, y, w, h in recover_rows(region):
            if any(abs(y - old_y) <= 3 and x < old_x + old_im.width and x + w > old_x
                   for old_y, old_x, old_im in boxes):
                continue
            boxes.append((y, x, region.crop((max(0,x-2), max(0,y-2),
                                             min(region.width,x+w+2), min(region.height,y+h+2)))))
        # 赤い文字はHPバーと白文字を横結合しない独立経路で拾う。
        from .red_labels import candidates as red_candidates
        ordinary_boxes=list(boxes)
        for y,x,crop in red_candidates(region):
            if ordinary_boxes and not any(abs(y-oy)<=max(64,crop.height*4) and x<ox+old.width and x+crop.width>ox for oy,ox,old in ordinary_boxes):
                continue
            if not any(abs(y-oy)<=3 and x<ox+old.width and x+crop.width>ox for oy,ox,old in boxes):
                boxes.append((y,x,crop))
        # 先に同じ板の断片を戻し、最後に別の板の境目で分ける。
        # 順番を逆にすると、スクロール名の内部空白を別アイテムにしてしまう。
        boxes = merge_fragments(region, boxes)
        boxes = remove_gauge_candidates(region, boxes)
        # ALTを押している間だけ出る品名板の列だけを残す。キャラクター・ペットの
        # 名札（文字だけで背景は床）は、ALTを押していない時も画面に出ているため除外。
        _, boxes = alt_display.select(boxes)
        if len(boxes) < 2:
            from .plate_recovery import recover
            for y,x,im in recover(region):
                if any(abs(y-oy)<=3 and x<ox+old.width and x+im.width>ox for oy,ox,old in boxes):
                    continue
                im.info['recovered_plate'] = True
                boxes.append((y,x,im))
        # Paired plate edges recover labels whose translucent backgrounds are
        # brightened by a red or blue flare. Keep the original color for OCR.
        from .bright_plates import recover as recover_bright
        for y,x,im in (recover_bright(region) if len(boxes)<2 else []):
            if any(abs(y-oy)<=5 and x<ox+old.width and x+im.width>ox
                   for oy,ox,old in boxes):
                continue
            boxes.append((y,x,im))
        pieces = []
        for y, x, im in sorted(boxes):
            left = x
            for piece in split_labels(im):
                normalized_width = piece.width
                if im.info.get('recovered_plate') or np.mean(np.asarray(piece).max(2) < 90) >= .20:
                    # 画面上の位置（検出範囲内の座標）。ALT表示中の複数フレームで同じ行を
                    # 対応付けるために使う。品名の判定には使わない。
                    piece.info['pos'] = (int(y), int(left), piece.width)
                    if recognition_scale != 1:
                        sx = original_region.width / region.width
                        sy = original_region.height / region.height
                        # 解析だけ縮小し、証拠・学習画像と位置は元キャプチャの画素に戻す。
                        rect = (round(max(0, left-2)*sx), round(max(0, y-2)*sy),
                                round(min(region.width, left-2+piece.width)*sx),
                                round(min(region.height, y-2+piece.height)*sy))
                        source_piece = original_region.crop(rect)
                        source_piece.info['pos'] = (round(y*sy), round(left*sx), source_piece.width)
                        source_piece.info['recognition_image'] = piece
                        source_piece.info['recognition_scale'] = recognition_scale
                        piece = source_piece
                    pieces.append(piece)
                left += normalized_width
        return pieces

    def recognize_template(self, image, mask=None):
        """確認済み画像との一致と次点との差を検証する。曖昧ならOCRへ回す。"""
        mask = ink(image) if mask is None else mask
        if mask is None:
            return None
        scores = sorted([(mask_similarity(mask, t), n, k) for n, k, t in self.templates], reverse=True)
        if not scores or scores[0][0] < 0.92:
            return None
        score, name, kind = scores[0]
        second = next((s for s, n, k in scores[1:] if (n, k) != (name, kind)), 0.0)
        if score - second < 0.035:
            return None
        return (name, self.store.data['overrides'].get(name, kind))

    def ocr_suggestions(self, images):
        """同梱の日本語対応OCRへ渡す。画像処理と見本学習から推論を分離。"""
        return suggestions(images)

    def analyze(self, image, cropped=False):
        """見本を優先し、未登録名のOCRは候補扱いにする。手動確認の必要性を保持する。"""
        image = image.convert('RGB')
        images = self.boxes(image, cropped) if cropped else self.boxes(image)
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
            labels.append({'name': name, 'kind': kind, 'raw': raw, 'image': im, 'fingerprint': key,
                           'pos': im.info.get('pos')})
        ocr_error = ''
        if unknown:
            try:
                suggestions = self.ocr_suggestions([im.info.get('recognition_image', im) for _, im, _ in unknown])
            except (OSError, RuntimeError, ValueError) as exc:
                suggestions = [''] * len(unknown)
                ocr_error = str(exc)
            for (i, im, key), raw in zip(unknown, suggestions):
                kind = 'excluded' if self.rules.classify(raw) == 'excluded' else 'review'
                labels[i].update(name=raw or '読取不明', kind=kind, raw=raw)
                # 一時的なOCR障害を覚えると、次のフレームで再試行できなくなる。
                if not ocr_error:
                    self.cache[key] = (labels[i]['name'], kind, raw)
            if len(self.cache) > 200:
                self.cache.clear()
        labels = [label for label in labels if normalize(label['raw']).lower() not in ('ctrl+f', 'ctrl+fキー')
                  and not is_hud_text(label['raw']) and not is_system_notice(label['raw'])]
        for label in labels:
            item = self.catalog.find(label['name'])
            label['registered'] = item is not None
            label['candidates'] = self.catalog.candidates(label['name'])
            if item:
                original = label['name']
                label['name'] = item['name']
                label['kind'] = self.catalog.classify(original)
        message = 'ALTの品名が見つかりません。' if not labels else f'{len(labels)}行を検出'
        if ocr_error:
            message += ' / OCRエラー：' + ocr_error
        return {'labels': labels, 'message': message}

    def learn(self, name, kind, image, *, run_id=None, row_index=None):
        """品名画像・扱い・選択行の修正を一度に保存。失敗時は全設定を戻す。"""
        name = normalize(name)
        if not name or kind not in ('material', 'excluded', 'review'):
            raise ValueError('品名と集計/除外/未確認を指定してください。')
        folder = self.store.folder / 'labels'
        folder.mkdir(exist_ok=True)
        digest = hashlib.sha256(image.tobytes() + name.encode('utf-8')).hexdigest()[:20]
        path = folder / (digest + '.png')
        image.save(path)
        rel = path.relative_to(self.store.folder).as_posix()
        previous = copy.deepcopy(self.store.data)
        # ほぼ同一の旧見本は読込時に新しい見本で置き換わるため、記録からも外す。
        # 残すと修正の度に見本一覧が伸び、照合と再読込が遅くなり続ける。
        new_mask = ink(image)
        def superseded(record):
            if record['path'] == rel:
                return True
            path = self.store.folder / record['path']
            if not path.exists():
                return False
            try:
                return mask_similarity(new_mask, self._mask(path)) >= 0.98
            except OSError:
                return False
        self.store.data['templates'] = [r for r in self.store.data['templates'] if not superseded(r)]
        self.store.data['templates'].append({'name': name, 'kind': kind, 'path': rel})
        self.store.data['overrides'][name] = kind
        if run_id is not None:
            run = self.store.find(run_id)
            run['rows'][row_index].pop('reviewed_kind', None)
            run['rows'][row_index].pop('resolved_name', None)
            run['rows'][row_index].update(name=name, kind=kind)
            run['status'] = 'review'
        try:
            self.store.save()
        except Exception:
            self.store.data = previous
            raise
        self.reload()

