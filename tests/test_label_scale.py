# Full gameplay samples are private and are not distributed in this repository.
from pathlib import Path as _FixturePath
import unittest as _fixture_unittest
if not (_FixturePath(__file__).resolve().parent / 'fixtures').exists() or not (_FixturePath(__file__).resolve().parents[1] / 'tools/benchmarks/video').exists():
    raise _fixture_unittest.SkipTest('非公開の提供画像を使う回帰テスト（配布前に別環境で検証済み）')

"""実キャプチャの倍率障害と、従来画像・証拠座標の回帰確認。"""
import tempfile
import unittest
from PIL import Image
from drop_tool.config import ROOT
from drop_tool.tracker import Store
from drop_tool.vision import Vision, CENTER
from drop_tool.label_scale import recognition_scale
from drop_tool.alt_display import quick_check


class LabelScaleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vision = Vision(Store(self.temp.name))

    def load(self, name):
        with Image.open(ROOT/'tests/fixtures/dpi'/name) as im:
            return im.convert('RGB')

    def region(self, im):
        return im.crop(tuple(round(v*s) for v,s in zip(CENTER, [im.width, im.height]*2)))

    def test_single_enlarged_item_and_original_pixels(self):
        im = self.load('single.png')
        region = self.region(im)
        self.assertEqual(recognition_scale(region), 2.)
        self.assertTrue(quick_check(region))
        result = self.vision.analyze(im)
        self.assertEqual([x['name'] for x in result['labels']], ['炎の糸'])
        row = result['labels'][0]
        y, x, w = row['pos']
        crop = row['image']
        self.assertGreater(crop.height, 27)
        self.assertEqual(crop.tobytes(), region.crop((x-4, y-4, x-4+w, y-4+crop.height)).tobytes())

    def test_center_scan_has_same_names_and_positions(self):
        im = self.load('single.png')
        full = self.vision.analyze(im)['labels']
        center = self.vision.analyze(self.region(im), cropped=True)['labels']
        self.assertEqual([(r['name'], r['pos']) for r in full], [(r['name'], r['pos']) for r in center])

    def test_green_equipment_and_white_materials_are_kept(self):
        rows = self.vision.analyze(self.load('green.png'))['labels']
        names = [r['name'] for r in rows]
        self.assertEqual(len(rows), 6)
        self.assertTrue(any(n.startswith('リファインドマジェスティ') for n in names))
        for n in ('ペルシウスランディングチェーンブレイド', '6段階赤い改造石', '炎の糸', '再生の粉'):
            self.assertIn(n, names)

    def test_resolution_alone_does_not_trigger_resizing(self):
        with Image.open(ROOT/'tools/benchmarks/video/video-alt-loot.png') as src:
            im = src.convert('RGB')
        canvas = Image.new('RGB', (3840,2160))
        canvas.paste(im,(1500,700))
        self.assertEqual(recognition_scale(canvas), 1.)
        self.assertEqual(len(Vision.boxes(None, canvas, cropped=True)), 8)

    def test_blank_frame_has_no_scale_or_items(self):
        im = Image.new('RGB', (3840,2160), (40,40,40))
        self.assertEqual(recognition_scale(im), 1.)
        self.assertFalse(quick_check(im))
        self.assertEqual(Vision.boxes(None, im), [])
