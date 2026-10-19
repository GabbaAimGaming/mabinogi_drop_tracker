import unittest
from pathlib import Path
from PIL import Image
from drop_tool.config import ROOT
from drop_tool.chest_shape import ChestShape

class ChestShapeTests(unittest.TestCase):
    def test_no_chest_from_blank_panels(self):
        detector=ChestShape()
        for size in ((32,32),(640,480),(1920,1080)):
            self.assertFalse(detector.detect(Image.new('RGB',size,(20,20,20)))['found'])

    def test_plate_context_requires_three_local_rows(self):
        box=(300,200,400,325)
        close=[(310,310,100,15),(310,340,100,15),(310,370,100,15)]
        far=[(10,600,100,15),(10,630,100,15),(10,660,100,15)]
        self.assertFalse(ChestShape.near_plates(box,close[:2]))
        self.assertFalse(ChestShape.near_plates(box,far))
        self.assertTrue(ChestShape.near_plates(box,close))

    def test_previously_missed_glowing_chest_without_model_training(self):
        source=ROOT.parents[1]/'work/4k-20261019/samples/20261018-024011-1b8dc35c/frame-00.png'
        if not source.exists():self.skipTest('非公開の提供画像が必要')
        detector=ChestShape()
        with Image.open(source) as im:
            result=detector.detect(im.convert('RGB'))
            self.assertTrue(result['found'])
            x0,y0,x1,y1=result['match']['box']
            self.assertTrue(1400<x0<x1<1750 and 950<y0<y1<1300)
            self.assertFalse(detector.detect(im.crop((0,0,3816,600)))['found'])

    def test_shape_asset_stays_small(self):
        self.assertLess((ROOT/'assets/chest-shape.npz').stat().st_size,4096)
