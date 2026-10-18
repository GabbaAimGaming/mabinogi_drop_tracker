# Full gameplay samples are private and are not distributed in this repository.
from pathlib import Path as _FixturePath
import unittest as _fixture_unittest
if not (_FixturePath(__file__).resolve().parent / 'fixtures').exists() or not (_FixturePath(__file__).resolve().parents[1] / 'tools/benchmarks/video').exists():
    raise _fixture_unittest.SkipTest('非公開の提供画像を使う回帰テスト（配布前に別環境で検証済み）')

"""横並び品名の実画像と、名称内の空白を区別する回帰テスト。"""
import tempfile
import unittest
from PIL import Image
import numpy as np
from drop_tool.label_images import split_labels, ocr_image, text_pixels
from drop_tool.tracker import ROOT, Store
from drop_tool.vision import Vision


class LabelImageTests(unittest.TestCase):
    def test_adjacent_short_names_are_separate_original_crops(self):
        # 元のゲーム画面を切り出した実画像。炎の糸と魔法の粉の背景板の間に隙間がある。
        im = Image.open(ROOT / 'tests/fixtures/adjacent-loot.png').convert('RGB')
        pair = im.crop((63, 44, 149, 58))
        parts = split_labels(pair)
        self.assertEqual(len(parts), 2)
        self.assertEqual(sum(p.width for p in parts), pair.width)
        combined = np.concatenate([np.asarray(p) for p in parts], axis=1)
        np.testing.assert_array_equal(combined, np.asarray(pair))

    def test_internal_space_in_enchant_name_is_not_split(self):
        im = Image.open(ROOT / 'tests/fixtures/adjacent-loot.png').convert('RGB')
        enchant = im.crop((33, 211, 220, 225))
        self.assertEqual(len(split_labels(enchant)), 1)

    def test_other_names_split_without_dictionary(self):
        # 文字列を知らなくても、背景板の区切りで分割できる。
        im = Image.new('RGB', (84, 14), 'black')
        from PIL import ImageDraw
        draw = ImageDraw.Draw(im)
        for left in (2, 44):
            for x in range(left, left + 30, 5):
                draw.rectangle((x, 3, x + 2, 10), fill='white')
        draw.rectangle((36, 0, 39, 13), fill=(120, 100, 100))
        self.assertEqual(len(split_labels(im)), 2)

    def test_old_labels_do_not_fragment(self):
        for path in (ROOT / 'references/labels').glob('*.png'):
            with self.subTest(path=path.name):
                self.assertEqual(len(split_labels(Image.open(path))), 1)

    def test_preprocessing_preserves_shape_and_does_not_invent_pixels(self):
        im = Image.open(ROOT / 'references/labels/00.png')
        result = ocr_image(im)
        self.assertEqual(result.size, im.size)
        np.testing.assert_array_equal(np.asarray(result)[:, :, 0] == 0, text_pixels(im))

    def test_full_detection_splits_pair_without_splitting_enchant(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = Vision(Store(tmp))
            screen = Image.new('RGB', (1920, 1080), (110, 80, 70))
            crop = Image.open(ROOT / 'tests/fixtures/adjacent-loot.png')
            screen.paste(crop, (600, 520))
            boxes = v.boxes(screen)
            self.assertEqual(len(boxes), 11)  # 発光背景のクロスボウも回収する。
            self.assertIn(187, [b.width for b in boxes])
            self.assertNotIn(86, [b.width for b in boxes])

    def test_ocr_failure_is_reported_and_not_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = Vision(Store(tmp))
            im = Image.open(ROOT / 'tests/fixtures/adjacent-loot.png').crop((63, 44, 100, 58))
            v.boxes = lambda screen: [im]
            v.recognize_template = lambda image: None
            def fail(images):
                raise RuntimeError('OCR unavailable')
            v.ocr_suggestions = fail
            result = v.analyze(im)
            self.assertIn('OCR unavailable', result['message'])
            self.assertEqual(result['labels'][0]['kind'], 'review')
            self.assertEqual(v.cache, {})
