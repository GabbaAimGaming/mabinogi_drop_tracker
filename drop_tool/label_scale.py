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
    del rgb,r,g,b
    joined = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((1, 13), 'uint8'))
    _, _, stats, _ = cv2.connectedComponentsWithStats(joined)
    candidates = []
    for x, y, w, h, area in stats[1:]:
        if not (7 <= h <= 44 and 2.5*h <= w <= 1200 and x >= 3 and y >= 3
                and x+w+3 <= region.width and y+h+3 <= region.height):
            continue
        edge = np.concatenate((pixels[y-2:y, x:x+w].reshape(-1, 3),
                               pixels[y+h:y+h+2, x:x+w].reshape(-1, 3)))
        dark = float(np.mean(edge.max(1) < 70))
        if dark < .65:
            continue
        candidates.append((int(x),int(y),int(w),int(h),dark))
    # 同じ文字サイズの縦列を優先する。横並びの百分率や孤立したHUDを
    # 多数の品名板より強い倍率の根拠にしない。
    votes = {}
    heights = {}
    for x,y,w,h,dark in candidates:
        neighbors = sum(1 for bx,by,bw,bh,_ in candidates
                        if abs(h-bh) <= max(3,h*.15) and h <= abs(y-by) <= h*4
                        and x < bx+bw and bx < x+w)
        if not neighbors and dark < .90:
            continue
        # 文字内容で24～29pxにばらつく同じフォントをまとめてから決める。
        bucket = next((key for key in votes if abs(key-h) <= max(3,key*.15)),h)
        votes[bucket] = votes.get(bucket,0.) + min(4.,w/h)*dark*(3 if neighbors else 1)
        heights.setdefault(bucket,[]).append(h)
    if not votes:
        from .red_labels import candidates as red_candidates
        reds=red_candidates(region,max_height=44)
        if not reds:return 1.0
        height=float(np.percentile([crop.height-4 for _,_,crop in reds],85))
        return (1.0 if height<=18 else min((1.5,1.75,2.,2.5,3.),key=lambda s:abs(height/s-14)))
    best = max(votes, key=votes.get)
    height = float(np.percentile(heights[best],85))
    return (1.0 if height <= 18 else min((1.5,1.75,2.,2.5,3.),key=lambda s:abs(height/s-14)))


def normalized(region):
    scale = recognition_scale(region)
    if scale == 1:
        return region, scale
    return region.resize((max(1, round(region.width/scale)),
                          max(1, round(region.height/scale))), Image.Resampling.LANCZOS), scale

