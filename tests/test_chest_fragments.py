import unittest
from pathlib import Path
from PIL import Image,ImageEnhance
from drop_tool.config import ROOT
from drop_tool.chest_fragments import ChestFragments

SAMPLES={
1:('20261018-014807-646232ae',(2070,740,2260,1020)),
2:('20261018-015615-b18cd77b',(1310,820,1670,1220)),
3:('20261018-020630-b7fcbb7d',(1610,874,1810,1170)),
6:('20261018-024825-6698e789',(1630,870,1900,1160)),
14:('20261018-212840-c110196b',(1670,880,1940,1210)),
16:('20261018-214122-938e6f3d',(1790,870,2000,1150)),
17:('20261018-214850-c51bd05c',(1820,890,2080,1170)),
24:('20261018-231441-e71cae80',(1670,920,1920,1210)),
}

def image(index):
    path=ROOT.parents[1]/'work/4k-20261019/samples'/SAMPLES[index][0]/'frame-00.png'
    if not path.exists():raise unittest.SkipTest('非公開の提供画像が必要')
    with Image.open(path) as im:return im.convert('RGB')

class ChestFragmentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.detector=ChestFragments()

    def test_all_eight_known_failures_locate_the_chest(self):
        for i,(_,expected) in SAMPLES.items():
            with self.subTest(index=i):
                r=self.detector.detect(image(i));self.assertTrue(r['found'])
                self.assertGreaterEqual(r['match']['score'],.90)
                self.assertTrue(all(abs(a-b)<12 for a,b in zip(expected,r['match']['box'])))

    def test_reference_photo_alone_is_insufficient_without_alt_context(self):
        self.assertFalse(self.detector.detect(image(24),rows=[])['found'])

    def test_affine_brightness_changes_do_not_require_the_same_pixels(self):
        for factor in (.8,1.1):
            self.assertTrue(self.detector.detect(ImageEnhance.Brightness(image(1)).enhance(factor))['found'])

    def test_no_chest_from_blank_or_chest_erased_with_remaining_alt(self):
        im=image(2);box=SAMPLES[2][1];box=(box[0]-40,box[1]-40,box[2]+40,box[3]+40)
        im.paste(im.crop((400,1200,400+box[2]-box[0],1200+box[3]-box[1])),box[:2])
        self.assertFalse(self.detector.detect(im)['found'])
        self.assertFalse(self.detector.detect(Image.new('RGB',(1920,1080)))['found'])
