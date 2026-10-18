"""画面解像度ではなく、暗い品名板の文字高から解析倍率を決める。"""
import cv2
import numpy as np
from PIL import Image


def recognition_scale(region):
    """通常文字はそのまま。拡大された板だけ標準の約14pxへ戻す。"""
    pixels = np.asarray(region.convert('RGB'))
    # 待機中にも使うため、4K画面をfloat64の3チャンネル配列へ展開しない。
    rgb = pixels.astype(np.uint16)
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    mask = ((rgb.min(2) > 175) | ((g > 120) & (g*2 > r*3) & (g*5 > b*7))).astype('uint8')
    del rgb, r, g, b
    joined = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((1, 13), 'uint8'))
    _, _, stats, _ = cv2.connectedComponentsWithStats(joined)
    votes = {}
    for x, y, w, h, area in stats[1:]:
        if not (7 <= h <= 44 and 2*h <= w <= 1200 and x >= 3 and y >= 3
                and x+w+3 <= region.width and y+h+3 <= region.height):
            continue
        edge = np.concatenate((pixels[y-2:y, x:x+w].reshape(-1, 3),
                               pixels[y+h:y+h+2, x:x+w].reshape(-1, 3)))
        if np.mean(edge.max(1) < 70) < .90:
            continue
        # 一つの長いHUD文字列だけが倍率を支配しないよう票数を制限する。
        scale = 1.0 if h <= 18 else min((1.5, 1.75, 2., 2.5, 3.), key=lambda s: abs(h/s-14))
        votes[scale] = votes.get(scale, 0.) + min(4., w/h)
    if not votes:
        return 1.0
    best = max(votes, key=votes.get)
    return best if votes[best] >= 2 else 1.0


def normalized(region):
    scale = recognition_scale(region)
    if scale == 1:
        return region, scale
    return region.resize((max(1, round(region.width/scale)),
                          max(1, round(region.height/scale))), Image.Resampling.LANCZOS), scale

