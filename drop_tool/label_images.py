"""品名分割・照合用マスクと比較表示。実OCRへの入力は元のカラー画像。"""
import numpy as np
import cv2
from PIL import Image


def text_pixels(image, include_red=False, include_cyan=False, include_purple=False):
    """白・緑の文字候補。比較・分割では水色も保持し、板の判定と分ける。"""
    a = np.asarray(image.convert('RGB')).astype(float)
    r,g,b=a[:,:,0],a[:,:,1],a[:,:,2]
    cyan=((g>140)&(b>140)&(r<g*.75)) if include_cyan else np.zeros(r.shape,dtype=bool)
    base=(a.min(2) > 175) | ((g > 120) & (g > r*1.5) & (g > b*1.4)) | cyan
    if include_purple:base |= purple_pixels(image)
    if not include_red:return base
    red=red_pixels(image)
    # 白・緑の品名に重なる赤い衣装や光で、照合マスクを変えない。
    return base | red if red.sum()>base.sum()*4 else base


def red_pixels(image):
    a=np.asarray(image.convert('RGB')).astype(np.int16)
    r,g,b=a[:,:,0],a[:,:,1],a[:,:,2]
    red=(r>140)&(r*5>g*7)&(r*5>b*6)
    if not red.any():return red
    # HPバーの長い横線が隣の赤い装備・髪とつながるのを防ぐ。
    # OCRへ渡す元画像は変えず、文字候補のマスクから横線だけを外す。
    line_width=max(28,round(image.width*.04))
    lines=cv2.morphologyEx(red.astype('uint8'),cv2.MORPH_OPEN,np.ones((1,line_width),np.uint8))
    red &= lines==0
    return red


def purple_pixels(image):
    """紫・ピンク寄りの文字色。純青や暗い影は含めず、横長ゲージを外す。"""
    a=np.asarray(image.convert('RGB')).astype(np.int16)
    r,g,b=a[:,:,0],a[:,:,1],a[:,:,2]
    mask=(r>100)&(b>140)&(r*4>g*5)&(b*4>g*5)&(r<b*1.6)
    lines=cv2.morphologyEx(mask.astype('uint8'),cv2.MORPH_OPEN,
                           np.ones((1,max(28,round(image.width*.04))),np.uint8))
    return mask & (lines==0)


def split_labels(image):
    """横結合された候補を背景板の切れ目で分割する。名称辞書に依存しない。

    文字のない列だけでは名称内の空白も切れるので、背景板より明るい
    縦の帯が2列以上、かつ高さの大半を通る場合だけ分離する。
    背景と板を区別できない場合は推測分割しない。
    """
    a = np.asarray(image.convert('RGB'))
    occupied = text_pixels(image,include_red=True,include_cyan=True,include_purple=True).any(axis=0)
    brightness = np.percentile(a.max(axis=2), 15, axis=0)
    cuts = [0]
    start = None
    for x, empty in enumerate(list(~occupied) + [False]):
        if empty and start is None:
            start = x
        elif not empty and start is not None:
            gap = brightness[start:x]
            # 別の品名板の継ぎ目は、両側の板の余白を含めて6px以上空く（参照画像で6～9px）。
            # 4～5pxは同じ品名の文字間で、半透明の板の奥が明るいと誤って分割していた
            # （録画：ケルティックトライボルトワ｜ンド）。
            if x - start >= 6:
                # 半透明の同じ板が明るい床に重なると、内部空白も75を超える。
                # 前後の板背景より明るい縦の隙間だけを切れ目にする。
                adjacent = np.concatenate((brightness[max(0,start-20):start],
                                           brightness[x:min(image.width,x+20)]))
                baseline = float(np.median(adjacent)) if adjacent.size else 0.
                bright = gap > max(75, baseline+22)
                if any(bright[:-1] & bright[1:]):
                    cuts.append((start + x) // 2)
            start = None
    cuts.append(image.width)
    pieces = [image.crop((left, 0, right, image.height))
              for left, right in zip(cuts, cuts[1:])]
    # 短い孤立した線を品名にしない。両側が品名として十分な幅の場合のみ分割。
    if len(pieces) > 1 and all(text_pixels(p,include_red=True,include_cyan=True,include_purple=True).any(0).sum() >= 12 for p in pieces):
        return pieces
    return [image]


def ocr_image(image):
    """比較表示用の白黒画像。旧関数名を維持するが、実OCRでは使用しない。"""
    mask = text_pixels(image,include_red=True,include_cyan=True,include_purple=True)
    return Image.fromarray(np.where(mask, 0, 255).astype('uint8')).convert('RGB')

