"""赤文字の模擬試験。実ゲームの赤ALTサンプルの代替とはしない。"""
import json,tempfile,unittest
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from drop_tool.config import ROOT
from drop_tool.label_images import text_pixels
from drop_tool.label_scale import recognition_scale
from drop_tool.alt_display import quick_check
from drop_tool.vision import Vision
from drop_tool.tracker import Store
from drop_tool.hud_text import is_system_notice


def red_plates(scale=1,color=(245,50,50),plate=True):
    entries=json.loads((ROOT/'references/labels.json').read_text(encoding='utf-8'))[:3]
    canvas=Image.new('RGB',(700,320),(110,100,90))
    draw=ImageDraw.Draw(canvas)
    if plate=='chat':draw.rectangle((40,40,650,250),fill=(8,8,8))
    for i,entry in enumerate(entries):
        im=Image.open(ROOT/entry['path']).convert('RGB');a=np.asarray(im).copy()
        mask=text_pixels(im)
        strength=a.max(2)[mask].astype(float)/255
        if not plate:a[:]=(110,100,90)
        a[mask]=(strength[:,None]*np.array(color)).astype('uint8')
        im=Image.fromarray(a);x,y=100,70+i*30
        if plate:draw.rectangle((x-6,y-3,x+im.width+6,y+im.height+3),fill=(8,8,8))
        canvas.paste(im,(x,y))
    if scale!=1:canvas=canvas.resize((canvas.width*scale,canvas.height*scale),Image.Resampling.NEAREST)
    return canvas,[x['name'] for x in entries]


class RedLabelTests(unittest.TestCase):
    def test_red_text_reaches_presence_and_japanese_recognition(self):
        with tempfile.TemporaryDirectory() as tmp:
            vision=Vision(Store(tmp))
            for scale in (1,2,3):
                for color in ((245,50,50),(200,65,70)):
                    im,names=red_plates(scale,color)
                    self.assertTrue(quick_check(im),(scale,color))
                    if scale>1:self.assertGreater(recognition_scale(im),1.)
                    labels=vision.analyze(im,cropped=True)['labels']
                    actual=[x['name'] for x in labels]
                    self.assertEqual(len(labels),3,(scale,color,actual))
                    for name in names[1:]:self.assertIn(name,actual,(scale,color,actual))
                    herb=next(x for x in labels if x['name'].startswith('マナハ'))
                    if herb['name']!=names[0]:self.assertEqual(herb['kind'],'review')

    def test_red_text_without_alt_plate_is_not_loot(self):
        im,_=red_plates(plate=False)
        self.assertFalse(quick_check(im))
        self.assertEqual(Vision.boxes(None,im,cropped=True),[])

    def test_large_red_effect_is_not_text(self):
        im=Image.new('RGB',(700,320),(12,12,12))
        ImageDraw.Draw(im).rectangle((100,45,400,250),fill=(245,45,45))
        self.assertFalse(quick_check(im))
        self.assertEqual(Vision.boxes(None,im,cropped=True),[])

    def test_red_lines_inside_a_shared_chat_panel_are_not_item_plates(self):
        im,_=red_plates(plate='chat')
        self.assertFalse(quick_check(im))
        self.assertEqual(Vision.boxes(None,im,cropped=True),[])

    def test_pickup_notice_is_not_an_item_name(self):
        self.assertTrue(is_system_notice('ージェム:サキュバスを1個を拾った。'))
        self.assertTrue(is_system_notice('<SYSTEM>: 人形が1000ゴールドを拾った。'))
        self.assertFalse(is_system_notice('フィニージェム:サキュバス'))
        self.assertFalse(is_system_notice('浄化された白い粉'))

    def test_actual_red_alt_enchant_in_submitted_4k_frame(self):
        source=ROOT.parents[1]/'work/4k-20261019/samples/20261018-231441-e71cae80/frame-00.png'
        if not source.exists():self.skipTest('非公開の提供画像が必要')
        with tempfile.TemporaryDirectory() as tmp:
            rows=Vision(Store(tmp)).analyze(Image.open(source))['labels']
            row=next(x for x in rows if x['name']=='専用エンチャントスクロール・巧みな')
            self.assertEqual(row['kind'],'review')
            self.assertTrue(row['registered'])
