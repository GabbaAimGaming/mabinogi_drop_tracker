"""ALTキーを押している間だけ出る「品名の黒い板」の判定。キー入力は読まない。

ゲームはALTキーの状態を他アプリへ渡さないため、画面の見た目で判断する。
2026-10-14の録画（1080p・60fps）で確認した特徴：

- ALT中は、地面の品名が半透明の黒い板の上に白・緑の文字で出る。
  板どうしは約15～20px間隔で縦に積み重なる（品が多いほど縦に長くなる）。
- ALTを離すと板は消え、キャラクター・ペットの名札（文字だけ、背景は床）に戻る。
  名札も白文字に黒い縁取りがあるため、従来の検出では品名として拾っていた。

判定は「板の暗さ」と「縦の積み重なり」で行う。名札は背景が床のため暗さが
0.3前後に留まり、近い位置に並んでも板のような一定間隔の縦列にはならない。
"""
import cv2
import numpy as np

from .label_images import text_pixels

# 板とみなす背景の暗さ（文字と縁取りを除いた画素のうち、最大値が60未満の割合）。
STRONG = 0.6
# 1枚だけの報酬でも読めるよう、十分に暗い単独の板は認める。
SINGLE = 0.9
# 縦に隣り合う板の間隔（上端の差）を、低い方の切り抜きの高さに対する比で許す範囲。
# 板は重ならずに積まれる（録画では高さ14pxに対し間隔15～20px）。上限は検出漏れの
# 1行を挟んでも列が途切れないよう広めに取る。名札どうしが重なる配置（比0.93）は除外。
PITCH = (1.0, 2.7)


def darkness(crop):
    """切り抜きの背景（文字の周囲1pxを除く）がどれだけ黒い板か。0～1。"""
    a = np.asarray(crop.convert('RGB'))
    near = cv2.dilate(text_pixels(crop,include_red=True,include_purple=True).astype('uint8'), np.ones((3, 3), 'uint8')).astype(bool)
    background = a[~near]
    if background.size == 0:
        return 0.0
    return float(np.mean(background.max(1) < 60))


def _stacked(a, b):
    (ya, xa, ca), (yb, xb, cb) = a, b
    pitch = abs(ya - yb)
    height = min(ca.height, cb.height)
    if not PITCH[0] * height <= pitch <= PITCH[1] * height:
        return False
    # 板の列は左右がそろわないことが多いので、横方向は重なりがあれば同じ列とみなす。
    return xa < xb + cb.width and xb < xa + ca.width


def select(candidates):
    """(y, x, 切り抜き)の候補から、ALT表示の品名板だけを返す。

    戻り値は (ALT表示があるか, 品名板の候補)。縦に積み重なった板の列に属する
    候補は、重なりで暗さが下がっていても残す。列に属さない名札などは外す。
    """
    if not candidates:
        return False, []
    dark = [darkness(crop) for _, _, crop in candidates]
    parent = list(range(len(candidates)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            if _stacked(candidates[i], candidates[j]):
                parent[root(i)] = root(j)
    groups = {}
    for i in range(len(candidates)):
        groups.setdefault(root(i), []).append(i)
    keep = set()
    for members in groups.values():
        strong = sum(dark[i] >= STRONG for i in members)
        if len(members) >= 2 and strong >= 2:
            keep.update(members)
        elif len(members) == 1:
            i = members[0]
            if dark[i] >= SINGLE and 12 <= candidates[i][2].height <= 19:
                keep.add(i)
    kept = [candidates[i] for i in sorted(keep)]
    return bool(kept), kept


class _Box:
    """quick_check用の軽量な候補（切り抜き画像の代わりに高さ・幅だけ持つ）。"""
    __slots__ = ('width', 'height')

    def __init__(self, width, height):
        self.width, self.height = width, height


def quick_check(region):
    """1/2に間引いた画像で、ALTの品名板の列がありそうかを高速に判定する。

    select()と同じ「暗い板」「縦の積み重なり」をゆるい条件で見る。Trueの時だけ
    本解析を行う。名札だけの画面では本解析を省けるため、待機中の負荷が下がる。
    """
    from .label_scale import normalized
    region, _ = normalized(region)
    a = np.asarray(region.convert('RGB'))[::2, ::2].astype(np.int16)
    if a.size == 0:
        return False
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    text = ((a.min(2) > 175) | ((g > 120) & (g * 2 > r * 3) & (g * 5 > b * 7))
            | ((g > 140) & (b > 140) & (r * 4 < g * 3)))
    darkmask = a.max(2) < 90
    dark = cv2.blur(darkmask.astype(np.float32), (5, 5))
    seeds = (text & (dark > .25)).astype(np.uint8)
    seeds = cv2.morphologyEx(seeds, cv2.MORPH_CLOSE, np.ones((1, 7), np.uint8))
    _, _, stats, _ = cv2.connectedComponentsWithStats(seeds)
    near = cv2.dilate(text.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    plate = (a.max(2) < 60) & ~near
    candidates, strong = [], []
    for x, y, w, h, _ in stats[1:]:
        if not (3 <= h <= 10 and w >= 12):
            continue
        y0, y1, x0, x1 = max(0, y - 1), y + h + 1, max(0, x - 1), x + w + 1
        background = ~near[y0:y1, x0:x1]
        score = plate[y0:y1, x0:x1][background].mean() if background.any() else 0.0
        candidates.append((y0, x0, _Box(x1 - x0, y1 - y0)))
        strong.append(score >= STRONG - 0.1)
    for i in range(len(candidates)):
        if not strong[i]:
            continue
        if any(strong[j] and _stacked(candidates[i], candidates[j])
               for j in range(len(candidates)) if j != i):
            return True
        if candidates[i][2].height >= 6:
            # 単独の板（報酬1品）もありうるため、十分に暗い1行は本解析へ回す。
            y0, x0, box = candidates[i]
            background = ~near[y0:y0 + box.height, x0:x0 + box.width]
            if background.any() and plate[y0:y0 + box.height, x0:x0 + box.width][background].mean() >= SINGLE:
                return True
    from .plate_recovery import recover
    if recover(region):
        return True
    from .bright_plates import recover as recover_bright
    if recover_bright(region):
        return True
    from .color_labels import purple, red
    if select(red(region))[0]:
        return True
    return bool(select(purple(region))[0])
