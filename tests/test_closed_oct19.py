"""Private chest crops embedded at native pixel size; no gameplay images shipped."""
import unittest
from PIL import Image, ImageEnhance
from drop_tool.config import ROOT
from drop_tool.chest_detector import ChestDetector

SAMPLES = ROOT.parents[1] / 'work/closed-chests-20261019'


@unittest.skipUnless((SAMPLES/'closed-15.png').exists(), '非公開の提出画像が必要')
class ClosedChestOctoberTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = ChestDetector()

    def canvas(self,index,size=(1280,720),offset=(450,230),negative=False,brightness=1):
        prefix='floor' if negative else 'closed'
        with Image.open(SAMPLES/f'{prefix}-{index:02}.png') as image:
            image=image.convert('RGB')
        if brightness!=1:
            image=ImageEnhance.Brightness(image).enhance(brightness)
        result=Image.new('RGB',size,(35,30,28))
        result.paste(image,offset)
        return result

    def test_sixteen_views_at_native_size_on_normal_and_4k_canvas(self):
        for index in range(16):
            for size,offset in (((1280,720),(450,230)),((3840,2160),(1750,950))):
                with self.subTest(index=index,size=size):
                    result=self.detector.detect(self.canvas(index,size,offset))
                    self.assertTrue(result['found'])
                    # Whole-reference projections can include an open lid or
                    # crop margins. Validate the actual inlier surface location.
                    l,t,r,b=result['match']['evidence_box']
                    with Image.open(SAMPLES/f'closed-{index:02}.png') as image:
                        self.assertTrue(offset[0]<=l<r<=offset[0]+image.width)
                        self.assertTrue(offset[1]<=t<b<=offset[1]+image.height)

    def test_chest_erased_crops_do_not_match_the_remaining_floor(self):
        for index in range(16):
            for size,offset in (((1280,720),(450,230)),((3840,2160),(1750,950))):
                with self.subTest(index=index,size=size):
                    self.assertFalse(self.detector.detect(self.canvas(index,size,offset,negative=True))['found'])

    def test_surface_features_tolerate_brightness_changes(self):
        for index in (3,5,11):
            for brightness in (.8,1.1):
                with self.subTest(index=index,brightness=brightness):
                    self.assertTrue(self.detector.detect(self.canvas(index,brightness=brightness))['found'])
