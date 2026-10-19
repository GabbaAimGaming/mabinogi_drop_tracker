# Gameplay samples stay private; validated separately before publication.
from pathlib import Path as _FixturePath
import unittest as _fixture_unittest
if not (_FixturePath(__file__).resolve().parent / 'fixtures').exists() or not (_FixturePath(__file__).resolve().parents[1] / 'tools/benchmarks/video').exists():
    raise _fixture_unittest.SkipTest('非公開の提出画像で別途検証済み')

"""スクロールの接尾名を別アイテムにした実画像の回帰検証。"""
import unittest
from PIL import Image
from drop_tool.vision import Vision
from drop_tool.config import ROOT

class ScrollFragmentTests(unittest.TestCase):
    def test_scroll_name_is_one_original_crop(self):
        screen=Image.new('RGB',(1920,1080),(110,80,70))
        with Image.open(ROOT/'tests/fixtures/scroll-loot.png') as crop:
            screen.paste(crop,(980,325))
        boxes=Vision.boxes(None,screen)
        self.assertEqual(len(boxes),16)
        self.assertEqual(boxes[1].tobytes(),screen.crop((1020,349,1207,363)).tobytes())
        self.assertEqual(boxes[2].tobytes(),screen.crop((1025,367,1201,381)).tobytes())
    def test_two_items_with_visible_background_seam_stay_separate(self):
        screen=Image.new('RGB',(1920,1080),(110,80,70))
        with Image.open(ROOT/'tests/fixtures/adjacent-loot.png') as crop:
            screen.paste(crop,(600,520))
        boxes=Vision.boxes(None,screen)
        self.assertEqual(len(boxes),11)
        self.assertIn(187,[b.width for b in boxes])
        self.assertNotIn(86,[b.width for b in boxes])
