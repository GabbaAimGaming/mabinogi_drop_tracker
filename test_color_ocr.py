"""OCR入力の色保持と元画像の非破壊性を確認する。"""
import unittest
from PIL import Image
from drop_tool.ocr_engine import make_atlas

class ColorOcrTests(unittest.TestCase):
    def test_color_is_preserved_and_source_is_unchanged(self):
        source = Image.new('RGB', (30, 12), (80, 150, 90))
        before = source.tobytes()
        atlas, height = make_atlas([source])
        self.assertEqual(atlas.getpixel((40, 25)), (80, 150, 90))
        self.assertEqual(source.tobytes(), before)
        self.assertEqual(atlas.getpixel((0, 0)), (0, 0, 0))
