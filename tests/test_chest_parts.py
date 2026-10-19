import unittest
from pathlib import Path
from PIL import Image,ImageDraw
from drop_tool.config import ROOT
from drop_tool.chest_parts import ChestParts
from drop_tool.chest_detector import ChestDetector


class ChestPartsTests(unittest.TestCase):
    def test_plain_dark_panels_and_colored_glows_do_not_confirm_a_chest(self):
        detector=ChestParts()
        for color in ((30,160,255),(185,50,255),(255,45,45),(255,205,40)):
            im=Image.new('RGB',(1000,700),(50,45,40));draw=ImageDraw.Draw(im)
            draw.rectangle((380,220,520,360),fill=(5,5,5),outline=(140,140,140),width=5)
            draw.rectangle((380,365,540,435),fill=(5,5,5),outline=(140,140,140),width=5)
            draw.rectangle((560,150,585,450),fill=color)
            self.assertFalse(detector.detect(im)['found'])

    def test_partial_reference_data_stays_small(self):
        folder=ROOT/'assets/chest-parts'
        self.assertLess(sum(p.stat().st_size for p in folder.iterdir() if p.is_file()),64*1024)

    def test_previously_missed_chest_and_original_coordinates(self):
        source=ROOT.parents[1]/'work/4k-20261019/samples/20261018-203239-e3fed254/frame-00.png'
        if not source.exists():self.skipTest('非公開の提供画像が必要')
        result=ChestDetector().detect(Image.open(source))
        self.assertTrue(result['found'])
        self.assertIn(result['search'], ('parts','shape'))
        x0,y0,x1,y1=result['match']['box']
        self.assertTrue(1750<x0<x1<2050 and 800<y0<y1<1150)
