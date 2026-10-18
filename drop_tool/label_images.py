"""品名分割・照合用マスクと比較表示。実OCRへの入力は元のカラー画像。"""
import numpy as np
from PIL import Image


def text_pixels(image):
    """従来と同じ白文字・緑文字を抽出する。背景を文字として補完しない。"""
    a = np.asarray(image.convert('RGB')).astype(float)
    return (a.min(2) > 175) | ((a[:, :, 1] > 120) &
        (a[:, :, 1] > a[:, :, 0] * 1.5) & (a[:, :, 1] > a[:, :, 2] * 1.4))


def split_labels(image):
    """横結合された候補を背景板の切れ目で分割する。名称辞書に依存しない。

    文字のない列だけでは名称内の空白も切れるので、背景板より明るい
    縦の帯が2列以上、かつ高さの大半を通る場合だけ分離する。
    背景と板を区別できない場合は推測分割しない。
    """
    a = np.asarray(image.convert('RGB'))
    occupied = text_pixels(image).any(axis=0)
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
                bright = gap > 75
                if any(bright[:-1] & bright[1:]):
                    cuts.append((start + x) // 2)
            start = None
    cuts.append(image.width)
    pieces = [image.crop((left, 0, right, image.height))
              for left, right in zip(cuts, cuts[1:])]
    # 短い孤立した線を品名にしない。両側が品名として十分な幅の場合のみ分割。
    if len(pieces) > 1 and all(text_pixels(p).any(0).sum() >= 12 for p in pieces):
        return pieces
    return [image]


def ocr_image(image):
    """比較表示用の白黒画像。旧関数名を維持するが、実OCRでは使用しない。"""
    mask = text_pixels(image)
    return Image.fromarray(np.where(mask, 0, 255).astype('uint8')).convert('RGB')

