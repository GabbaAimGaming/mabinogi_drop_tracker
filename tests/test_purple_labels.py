import tempfile
import unittest
from unittest.mock import Mock
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from drop_tool.label_images import text_pixels,split_labels
from drop_tool.purple_labels import candidates
from drop_tool.alt_display import quick_check
from drop_tool.label_scale import recognition_scale
from drop_tool.vision import Vision
from drop_tool.tracker import Store

PURPLE=(195,80,245)


def plate(text='PURPLE ITEM NAME',color=PURPLE):
    font=ImageFont.load_default(size=20)
    bbox=font.getbbox(text)
    im=Image.new('RGB',(bbox[2]+12,20),(10,10,10))
    ImageDraw.Draw(im).text((6,3-bbox[1]),text,font=font,fill=color)
    return im


def scene(rows=3):
    im=Image.new('RGB',(600,300),(110,90,75))
    for i in range(rows):im.paste(plate(),(170,80+i*25))
    return im


class PurpleLabelTests(unittest.TestCase):
    def test_purple_mask_keeps_letters_but_not_pure_blue_or_solid_gauge(self):
        self.assertTrue(text_pixels(plate(),include_purple=True).any())
        self.assertFalse(text_pixels(plate(),include_purple=False).any())
        self.assertFalse(text_pixels(plate(color=(30,70,240)),include_purple=True).any())
        self.assertFalse(text_pixels(Image.new('RGB',(100,10),PURPLE),include_purple=True).any())

    def test_purple_plate_reaches_detection_and_alt_presence(self):
        self.assertEqual(len(candidates(scene())),3)
        self.assertTrue(quick_check(scene()))
        self.assertTrue(quick_check(scene(1)))

    def test_distinct_purple_names_do_not_share_a_white_artifact_cache_key(self):
        with tempfile.TemporaryDirectory() as folder:
            v=Vision(Store(folder));v.templates=[];v.boxes=lambda im:[im]
            v.ocr_suggestions=Mock(side_effect=[['紫装備A'],['紫装備B']])
            first=v.analyze(plate('HAMMER'))['labels'][0]
            second=v.analyze(plate('STAFF'))['labels'][0]
            self.assertNotEqual(first['fingerprint'],second['fingerprint'])
            self.assertEqual(second['name'],'紫装備B')

    def test_full_pipeline_keeps_original_color_for_ocr(self):
        with tempfile.TemporaryDirectory() as folder:
            v=Vision(Store(folder));v.templates=[]
            seen=[]
            def ocr(images):
                seen.extend(images)
                return ['紫の装備']*len(images)
            v.ocr_suggestions=ocr
            result=v.analyze(scene(),cropped=True)
            self.assertEqual(len(result['labels']),3)
            self.assertTrue(any(np.any(np.all(np.asarray(im)==PURPLE,axis=2)) for im in seen))

    def test_purple_icons_flares_and_chat_without_individual_plates_are_rejected(self):
        for variant in ('icons','flare','chat'):
            im=Image.new('RGB',(600,300),(110,90,75));d=ImageDraw.Draw(im)
            if variant=='icons':
                for x in (180,220,260):d.ellipse((x,100,x+14,114),fill=PURPLE)
            elif variant=='flare':d.ellipse((170,70,350,220),fill=PURPLE)
            else:
                d.rectangle((0,50,599,250),fill=(10,10,10))
                for i in range(3):im.paste(plate(),(170,80+i*25))
            self.assertEqual(candidates(im),[],variant)

    def test_two_times_purple_only_plates_select_scale(self):
        doubled=scene().resize((1200,600),Image.Resampling.NEAREST)
        self.assertEqual(recognition_scale(doubled),2.)

    def test_japanese_glyphs_recolored_purple_reach_real_ocr_and_reference_matching(self):
        from tests.test_red_labels import red_plates
        with tempfile.TemporaryDirectory() as folder:
            v=Vision(Store(folder))
            for scale in (1,2,3):
                for color in (PURPLE,(235,100,220)):
                    image,names=red_plates(scale,color)
                    self.assertTrue(quick_check(image),(scale,color))
                    result=v.analyze(image,cropped=True)['labels']
                    actual=[r['name'] for r in result]
                    self.assertEqual(len(result),3,(scale,color,actual))
                    for name in names[1:]:self.assertIn(name,actual,(scale,color,actual))

    def test_neighboring_purple_plates_split_and_keep_pixels(self):
        image=Image.new('RGB',(84,14),'black');draw=ImageDraw.Draw(image)
        for left in (2,44):
            for x in range(left,left+30,5):draw.rectangle((x,3,x+2,10),fill=PURPLE)
        draw.rectangle((36,0,39,13),fill=(120,100,100))
        parts=split_labels(image);self.assertEqual(len(parts),2)
        np.testing.assert_array_equal(np.concatenate([np.asarray(p) for p in parts],axis=1),np.asarray(image))
