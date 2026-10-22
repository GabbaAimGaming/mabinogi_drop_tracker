"""発光の中央ではなく左右の箱表面を確認し、片側・黒い板・UIで開始しない。"""
import unittest

import numpy as np
from PIL import Image, ImageDraw

from drop_tool.chest_fragments import ChestFragments
from drop_tool.config import ROOT


class ChestRimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = ChestFragments()
        # 左右の縁の判定だけを検証する。他の有効な箱見本による救済は使わない。
        cls.detector.templates = []
        cls.rows = [(800, 480, 130, 18), (800, 510, 130, 18), (800, 540, 130, 18)]

    def reference(self, index=1):
        with np.load(ROOT / f'assets/chest-fragments/glow-rim-{index:02}.npz', allow_pickle=False) as data:
            return data['gray'].copy(), data['groups'].copy()

    def scene(self, patch):
        image = Image.new('RGB', (1920, 1080), (40, 35, 30))
        image.paste(Image.fromarray(patch).convert('RGB'), (800, 350))
        return image

    def test_both_rims_and_alt_context_confirm_all_three_references(self):
        for index in (1, 2, 3):
            gray, _ = self.reference(index)
            result = self.detector.detect(self.scene(gray), self.rows)
            self.assertTrue(result['found'], index)
            self.assertEqual(result['match']['evidence'], 'two-rim-surfaces')
            self.assertFalse(self.detector.detect(self.scene(gray), [])['found'])

    def test_one_rim_alone_or_displaced_rims_do_not_confirm(self):
        gray, groups = self.reference()
        for group in groups:
            patch = gray.copy(); patch[group > 0] = 25
            self.assertFalse(self.detector.detect(self.scene(patch), self.rows)['found'])
        # 元と違う相対位置へ片側だけ移しても、左右が同じ箱にそろったとは見なさない。
        patch = gray.copy(); patch[groups[1] > 0] = 25
        displaced = np.roll(groups[1], 12, axis=0) > 0
        shifted = np.roll(gray, 12, axis=0)
        patch[displaced] = shifted[displaced]
        self.assertFalse(self.detector.detect(self.scene(patch), self.rows)['found'])

    def test_light_in_the_masked_center_does_not_hide_the_rims(self):
        gray, groups = self.reference()
        # 判定で使わない中央の発光が変わっても、縁の模様はそのまま照合できる。
        patch = gray.copy(); patch[groups.max(axis=0) == 0] = 255
        self.assertTrue(self.detector.detect(self.scene(patch), self.rows)['found'])

    def test_plain_dark_rectangle_and_bright_border_are_insufficient(self):
        for width in (2, 3, 5, 8):
            image = Image.new('RGB', (1920, 1080), (40, 35, 30))
            draw = ImageDraw.Draw(image)
            draw.rectangle((800, 350, 880, 420), fill=(5, 5, 5), outline=(145, 145, 145), width=width)
            draw.rectangle((825, 375, 855, 430), fill=(90, 190, 255))
            self.assertFalse(self.detector.detect(image, self.rows)['found'])

    def test_brightness_change_keeps_surface_matching_and_assets_stay_small(self):
        gray, _ = self.reference()
        patch = np.clip(gray.astype('float32') * .8 + 10, 0, 255).astype('uint8')
        self.assertTrue(self.detector.detect(self.scene(patch), self.rows)['found'])
        files = list((ROOT / 'assets/chest-fragments').glob('glow-rim-*.npz'))
        files += list((ROOT / 'assets/chests').glob('open-glow-purple-*.npz'))
        self.assertEqual(len(files), 5)
        self.assertLess(sum(p.stat().st_size for p in files), 32 * 1024)
