"""Regression checks against privately held samples; source images are not distributed."""
import tempfile
import unittest

from PIL import Image, ImageEnhance

from drop_tool.config import ROOT
from drop_tool.chest_detector import ChestDetector
from drop_tool.chest_fragments import ChestFragments
from drop_tool.tracker import Store
from drop_tool.vision import Vision

SAMPLES = ROOT.parents[1] / 'work/4k-new-20261019/samples'


@unittest.skipUnless(SAMPLES.exists(), '非公開の提出画像が必要')
class Next4KSamplesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = sorted(SAMPLES.iterdir())
        cls.detector = ChestDetector()

    def frame(self, index):
        with Image.open(self.paths[index]/'frame-00.png') as image:
            return image.convert('RGB')

    def test_all_eight_chests_and_previously_missed_positions(self):
        for index in range(8):
            with self.subTest(index=index):
                result = self.detector.detect(self.frame(index))
                self.assertTrue(result['found'])
                if index in (0,2,7):
                    expected = {0:(1998,922,2147,1180), 2:(1320,750,1500,940),
                                7:(1735,800,1885,1025)}[index]
                    self.assertTrue(all(abs(a-b)<15 for a,b in
                                        zip(result['match']['box'],expected)))

    def test_new_frame_evidence_still_requires_alt_and_survives_brightness_change(self):
        detector = ChestFragments()
        self.assertFalse(detector.detect(self.frame(0), rows=[])['found'])
        for index in (0,2,7):
            for brightness in (.8,1.1):
                with self.subTest(index=index,brightness=brightness):
                    frame = ImageEnhance.Brightness(self.frame(index)).enhance(brightness)
                    self.assertTrue(detector.detect(frame)['found'])

    def test_cyan_equipment_and_missing_powder_prefix(self):
        with tempfile.TemporaryDirectory() as folder:
            vision = Vision(Store(folder))
            for index, expected in ((0,'リファインドボヘミアン帽子(女性用)'),
                                    (2,'ペルシウスブルータルウォーハンマー'),
                                    (6,'浄化された白い粉')):
                with self.subTest(index=index):
                    names = [r['name'] for r in vision.analyze(self.frame(index))['labels']]
                    self.assertIn(expected,names)
                    if index==2:
                        self.assertNotIn('ペルシウスランディングチェーンブレイド',names)
