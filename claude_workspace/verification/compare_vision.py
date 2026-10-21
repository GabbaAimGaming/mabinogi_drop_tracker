"""旧(red_labels/purple_labels)と新(color_labels)で認識の途中結果を比較する。引数：リポジトリ、出力json"""
import hashlib, json, random, sys, tempfile
repo, out = sys.argv[1], sys.argv[2]
sys.path[:0] = [repo, repo + '/tests']
import _headless; _headless.install()
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from drop_tool.tracker import Store
from drop_tool.vision import Vision
from drop_tool.alt_display import quick_check
from drop_tool.label_scale import recognition_scale
try:
    from drop_tool.color_labels import red, purple
except ImportError:
    from drop_tool.red_labels import candidates as red
    from drop_tool.purple_labels import candidates as purple
from test_red_labels import red_plates
from test_purple_labels import scene as purple_scene

refs = [Image.open(f'{repo}/references/labels/{i:02d}.png').convert('RGB') for i in range(13)]
FONTS = [ImageFont.load_default(size=s) for s in (11, 12, 13, 14, 16, 22, 28)]
COLORS = [(245, 50, 50), (220, 40, 40), (200, 90, 230), (170, 70, 220), (150, 60, 200), (255, 255, 255),
          (120, 255, 120), (80, 230, 255), (60, 60, 255), (255, 160, 60)]


def fuzz(seed):
    r = random.Random(seed)
    w, h = r.choice([(640, 400), (900, 560), (1280, 720)])
    floor = tuple(r.randint(30, 160) for _ in range(3))
    im = Image.new('RGB', (w, h), floor)
    d = ImageDraw.Draw(im)
    for _ in range(r.randint(0, 6)):  # 発光・床の模様
        x, y = r.randrange(w), r.randrange(h)
        d.ellipse((x, y, x + r.randint(20, 300), y + r.randint(10, 200)), fill=tuple(r.randint(0, 255) for _ in range(3)))
    x0 = r.randint(20, w // 2)
    y = r.randint(20, h // 3)
    for _ in range(r.randint(0, 6)):  # 品名板の列
        font = r.choice(FONTS)
        if r.random() < .3:
            label = r.choice(refs)
            if r.random() < .5:
                label = label.resize((label.width * 2, label.height * 2))
            im.paste(label, (x0 + r.randint(-30, 30), y))
            y += label.height + r.randint(2, 30)
            continue
        text = ''.join(r.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefg') for _ in range(r.randint(3, 20)))
        tw, th = d.textbbox((0, 0), text, font=font)[2:]
        px, py = x0 + r.randint(-30, 30), y
        if r.random() < .8:
            d.rectangle((px - 4, py - 4, px + tw + 4, py + th + 6), fill=tuple(r.randint(0, 40) for _ in range(3)))
        d.text((px, py), text, font=font, fill=r.choice(COLORS))
        y += th + r.randint(6, 30)
        if y > h - 40:
            break
    for _ in range(r.randint(0, 3)):  # HPバー・ゲージ
        x, yy = r.randrange(w - 100), r.randrange(h - 10)
        d.rectangle((x, yy, x + r.randint(40, 300), yy + r.randint(3, 12)), fill=r.choice(COLORS))
    return im


def sig(items):
    return [(int(y), int(x), crop.size, hashlib.md5(crop.tobytes()).hexdigest()[:10]) for y, x, crop in items]


def pieces(ps):
    return [(p.info.get('pos'), p.size, hashlib.md5(p.tobytes()).hexdigest()[:10], bool(p.info.get('recovered_plate')))
            for p in ps]


images = {}
for scale in (1, 2):
    for color in ((245, 50, 50), (200, 60, 60)):
        for plate in (True, False, 'chat'):
            images[f'red{scale}{color}{plate}'] = red_plates(scale, color, plate)[0]
for rows in (1, 2, 3, 5):
    images[f'purple{rows}'] = purple_scene(rows)
for seed in range(300):
    images[f'fuzz{seed}'] = fuzz(seed)

vision = Vision(Store(tempfile.mkdtemp()))
result = {}
for name, im in images.items():
    result[name] = {
        'red': sig(red(im)), 'purple': sig(purple(im)),
        'red44': sig(red(im, max_height=44)), 'purple44': sig(purple(im, max_height=44)),
        'boxes': pieces(vision.boxes(im)), 'boxes_cropped': pieces(vision.boxes(im, cropped=True)),
        'quick': bool(quick_check(im)), 'scale': recognition_scale(im),
    }
json.dump(result, open(out, 'w'), sort_keys=True)
print(len(result), 'images;',
      'red hits', sum(bool(v['red']) for v in result.values()),
      'purple hits', sum(bool(v['purple']) for v in result.values()),
      'boxes nonempty', sum(bool(v['boxes']) for v in result.values()),
      'quick true', sum(v['quick'] for v in result.values()),
      'scale!=1', sum(v['scale'] != 1 for v in result.values()))
