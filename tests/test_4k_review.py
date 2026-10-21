# Gameplay samples stay private; validated separately before publication.
from pathlib import Path as _FixturePath
import unittest as _fixture_unittest
if not (_FixturePath(__file__).resolve().parent / 'fixtures').exists() or not (_FixturePath(__file__).resolve().parents[1] / 'tools/benchmarks/video').exists():
    raise _fixture_unittest.SkipTest('非公開の提出画像で別途検証済み')

"""提供された原寸画像による回帰。画像は公開対象外。"""
from pathlib import Path
import unittest,tempfile
from PIL import Image
from drop_tool.config import ROOT
from drop_tool.tracker import Store
from drop_tool.vision import Vision,CENTER
from drop_tool.label_scale import recognition_scale
from drop_tool.chest_detector import ChestDetector

FOLDER=ROOT/'tests/fixtures/4k-1019'

@unittest.skipUnless(FOLDER.exists(),'非公開の4K提供画像が必要')
class FourKReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.vision=Vision(Store(self.temp.name))

    def test_elemental_hud_does_not_override_loot_scale(self):
        for name in ['020630','023305']:
            im=Image.open(FOLDER/(name+'.png')).convert('RGB')
            region=im.crop(tuple(round(v*s) for v,s in zip(CENTER,[im.width,im.height]*2)))
            self.assertEqual(recognition_scale(region),2.0)
            rows=self.vision.analyze(im)['labels']
            self.assertIn('再生の粉',[x['name'] for x in rows])
            self.assertFalse(any('%' in x['name'] for x in rows))

    def test_orb_and_fynni_are_complete_labels(self):
        im=Image.open(FOLDER/'214122.png').convert('RGB')
        rows=self.vision.analyze(im)['labels'];names=[x['name'] for x in rows]
        self.assertIn('ペルシウスアークトゥルスオーブ',names)
        self.assertIn('フィニージェム:ゴースト',names)
        self.assertNotIn('フィニ',names)
        self.assertFalse(any('%' in name for name in names))
        self.assertEqual(next(x for x in rows if x['name']=='ペルシウスアークトゥルスオーブ')['kind'],'review')

    def test_frontal_chest_and_original_frame_coordinates(self):
        im=Image.open(FOLDER/'025525.png').convert('RGB')
        result=ChestDetector().detect(im)
        self.assertTrue(result['found'])
        x0,y0,x1,y1=result['match']['box']
        self.assertTrue(1500<x0<x1<1850 and 800<y0<y1<1200)
