"""白・緑以外の色文字（赤・紫）の品名の補助候補。元画像は変更しない。

両色で共通の条件：
- 色の画素を横に結合した行が、高さ7～max_height、幅25～max(550, max_height*40)、画面端から3px以上内側。
- 行の高さの45%以上・面積3以上の字形が3つ以上ある。
- 上下2pxの縁の72%以上が暗い（品名板の黒い縁）。
- 左右の外側（pad=max(8,h)の幅）が、板の背景より明るい画素を35%以上含む。
  チャット欄は広い暗い領域の中に行が並ぶため、板の外側の床へ戻ることを必須にする。
色ごとの条件は、字形の密度の範囲、白・緑文字に対する色画素の比、字形の形の追加条件。
"""
import cv2
import numpy as np

from .label_images import purple_pixels, red_pixels, text_pixels


def red(region, max_height=18):
    """HPバーや色付きの床、白・緑品名の脇の赤い装備や光を除く。"""
    return _candidates(region, red_pixels, max_height, density=(.12, .75), dominance=4)


def purple(region, max_height=18):
    """アイコンやゲージを避けるため、字形は幅が高さの2倍以下で、外接矩形を塗りつぶさないものに限る。"""
    return _candidates(region, purple_pixels, max_height, density=(.08, .70), dominance=1.2,
                       letter=lambda w, h, area, row: w <= row * 2 and area < w * h * .85)


def _candidates(region, pixels, max_height, *, density, dominance, letter=None):
    a = np.asarray(region.convert('RGB'))
    raw = pixels(region).astype('uint8')
    joined = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, np.ones((1, 13), np.uint8))
    _, _, stats, _ = cv2.connectedComponentsWithStats(joined)
    result = []
    for x, y, w, h, _ in stats[1:]:
        if not (7 <= h <= max_height and 25 <= w <= max(550, max_height * 40)
                and x >= 3 and y >= 3 and x + w + 3 <= region.width and y + h + 3 <= region.height):
            continue
        glyph = raw[y:y + h, x:x + w]
        # ほぼ空の横線・塗りつぶし・単一の装備エフェクトを候補にしない。
        if not density[0] < float(glyph.mean()) < density[1]:
            continue
        _, _, letters, _ = cv2.connectedComponentsWithStats(glyph)
        if sum(1 for _, _, lw, lh, area in letters[1:]
               if lh >= h * .45 and area >= 3 and (letter is None or letter(lw, lh, area, h))) < 3:
            continue
        crop = region.crop((x - 2, y - 2, x + w + 2, y + h + 2))
        if pixels(crop).sum() <= text_pixels(crop).sum() * dominance:
            continue
        edge = np.concatenate((a[y - 2:y, x:x + w].reshape(-1, 3), a[y + h:y + h + 2, x:x + w].reshape(-1, 3)))
        if np.mean(edge.max(1) < 70) < .72:
            continue
        background = float(np.percentile(np.asarray(crop).max(2), 15))
        pad = max(8, h)
        sides = (a[y:y + h, max(0, x - 2 * pad):max(0, x - pad)],
                 a[y:y + h, min(region.width, x + w + pad):min(region.width, x + w + 2 * pad)])
        if not all(side.size and np.mean(side.max(2) > background + 12) >= .35 for side in sides):
            continue
        result.append((int(y), int(x), crop))
    return result
