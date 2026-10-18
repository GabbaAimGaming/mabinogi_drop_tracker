"""OCR入力の色保持と元画像の非破壊性を確認する。"""
import unittest
from PIL import Image
from drop_tool.ocr_engine import prepare_image

class ColorOcrTests(unittest.TestCase):
    def test_color_is_preserved_and_source_is_unchanged(self):
        source = Image.new('RGB', (30, 12), (80, 150, 90))
        before = source.tobytes()
        prepared = prepare_image(source)
        self.assertEqual(tuple(prepared[10, 10]), (90, 150, 80))
        self.assertEqual(prepared.shape, (36, 90, 3))
        self.assertEqual(source.tobytes(), before)
