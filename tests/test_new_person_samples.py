"""Private development samples; no player screenshots are shipped in the repository."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from drop_tool.config import ROOT
from drop_tool.chest_detector import ChestDetector
from drop_tool.tracker import Store
from drop_tool.vision import Vision

SAMPLES = ROOT.parents[1] / 'work/new-person-20261019/samples'


@unittest.skipUnless(SAMPLES.exists(), '非公開の提出画像が必要')
class NewPersonSamplesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = sorted(SAMPLES.iterdir())
        cls.detector = ChestDetector()

    def frame(self, index):
        with Image.open(self.paths[index] / 'frame-00.png') as image:
            return image.convert('RGB')

    def test_previously_missed_chest_angles(self):
        # Each manually inspected crop contains the real chest, not a UI panel.
        boxes = {6:(1080,340,1240,530), 7:(980,340,1180,570),
                 11:(850,300,1110,550), 15:(540,330,820,690),
                 16:(540,330,820,690)}
        for index, expected in boxes.items():
            with self.subTest(index=index):
                result = self.detector.detect(self.frame(index))
                self.assertTrue(result['found'])
                x0,y0,x1,y1 = result['match']['box']
                self.assertLess(abs((x0+x1)/2-(expected[0]+expected[2])/2), 45)
                self.assertLess(abs((y0+y1)/2-(expected[1]+expected[3])/2), 45)

    def test_red_glow_preserves_red_and_cyan_item_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            vision = Vision(Store(folder))
            for index in (15,16):
                with self.subTest(index=index):
                    labels = vision.analyze(self.frame(index))['labels']
                    names = {row['name'] for row in labels}
                    self.assertIn('専用エンチャントスクロール・楽園', names)
                    self.assertIn('ペルシウスミスティックスタッフ', names)
                    self.assertGreaterEqual(len(labels), 5)
