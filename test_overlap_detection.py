"""実際の発光・重なりを含むPNGの回帰検証。OCRの正解率とは別に検証する。"""
import unittest
from PIL import Image
from drop_tool.vision import Vision
from drop_tool.tracker import ROOT

class OverlapTests(unittest.TestCase):
    def test_eleven_rows_without_blue_character_name(self):
        crop = Image.open(ROOT/'references/overlapping-loot.png').convert('RGB')
        screen = Image.new('RGB',(1920,1080),(110,80,70))
        screen.paste(crop,(800,380))
        boxes = Vision.boxes(None,screen)
        self.assertEqual(len(boxes),11)
        # 最初は品名。上の青い名前は切り出されていない。
        self.assertEqual(boxes[0].tobytes(),screen.crop((866,426,999,440)).tobytes())
        self.assertTrue(any(b.width>=260 for b in boxes))
    def test_plain_background_does_not_create_items(self):
        self.assertEqual(Vision.boxes(None,Image.new('RGB',(1920,1080),(110,80,70))),[])
