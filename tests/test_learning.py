"""修正の自動学習、容量上限、曖昧な画像の除外と保存失敗の回復。"""
import copy
import tempfile
import unittest
import shutil
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageFont
from drop_tool import learning
from drop_tool.tracker import Store
from drop_tool.item_catalog import ItemCatalog
from drop_tool.item_registration import assign, unlink
from drop_tool.vision import Vision


def plate(text='TEST ITEM'):
    image=Image.new('RGB',(170,26),(12,12,12))
    ImageDraw.Draw(image).text((5,3),text,font=ImageFont.load_default(size=18),fill='white')
    return image


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name);self.catalog=ItemCatalog(self.store)
        self.name='魔力の黄金の糸'

    def test_normal_correction_learns_official_name_and_duplicate_does_not_grow(self):
        for _ in range(3):assign(self.catalog,'誤読',self.name,'material',image=plate())
        rows=self.store.data['templates'];self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['name'],self.name)
        self.assertEqual(len(list((self.store.folder/'labels').glob('*.png'))),1)
        unlink(self.catalog,['誤読'])
        self.assertEqual(Vision(Store(self.store.folder)).recognize_template(plate())[0],self.name)

    def test_same_glyphs_with_different_background_replace_old_file(self):
        first=plate();second=plate();second.putpixel((169,25),(24,24,24))
        assign(self.catalog,'誤読',self.name,'material',image=first)
        old=self.store.folder/self.store.data['templates'][0]['path']
        assign(self.catalog,'誤読',self.name,'material',image=second)
        self.assertFalse(old.exists());self.assertEqual(len(self.store.data['templates']),1)

    def test_blank_multiline_and_full_screenshot_never_learn(self):
        multi=Image.new('RGB',(170,65),'black');multi.paste(plate(),(0,0));multi.paste(plate(),(0,35))
        for image in (Image.new('RGB',(40,20),'white'),Image.new('RGB',(1920,1080)),multi):
            assign(self.catalog,'誤読',self.name,'excluded',image=image)
        self.assertEqual(self.store.data['templates'],[])
        self.assertEqual(self.catalog.classify(self.name),'excluded')

    def test_unconfirmed_kind_and_shared_split_image_never_learn(self):
        assign(self.catalog,'誤読',self.name,'review',image=plate())
        run=self.store.new_run('アルビ','HD','使用')
        run['rows']=[{'name':'a','kind':'review','image':'evidence/shared.png'},
                     {'name':'b','kind':'review','image':'evidence/shared.png'}]
        assign(self.catalog,'a',self.name,'material',image=plate(),run_id=run['id'],row_index=0)
        self.assertEqual(self.store.data['templates'],[])

    def records(self,count):
        folder=self.store.folder/'labels';folder.mkdir(exist_ok=True)
        result=[]
        for i in range(count):
            path=folder/('auto-'+format(i,'024x')+'.png');plate(str(i)).save(path)
            result.append({'name':str(i),'kind':'material','path':'labels/'+path.name})
        return result

    def test_per_item_count_global_count_and_bytes_keep_newest(self):
        records=self.records(8)
        for row in records[:5]:row['name']=self.name
        self.assertEqual(len(learning.bounded(self.store,records)),6)
        with patch.object(learning,'MAX_SAMPLES',2):
            self.assertEqual(learning.bounded(self.store,records),records[-2:])
        size=(self.store.folder/records[-1]['path']).stat().st_size
        with patch.object(learning,'MAX_BYTES',size):
            self.assertEqual(learning.bounded(self.store,records),records[-1:])

    def test_maintenance_preserves_unrelated_and_evidence_files(self):
        rows=self.records(5)
        for row in rows:row['name']=self.name
        self.store.data['templates']=rows;self.store.save()
        foreign=self.store.folder/'labels/user-image.png';foreign.write_bytes(b'keep')
        orphan=self.store.folder/('labels/'+'f'*20+'.png');orphan.write_bytes(b'old orphan')
        evidence=self.store.folder/'evidence';evidence.mkdir();(evidence/'keep.png').write_bytes(b'keep')
        learning.maintain(self.store)
        self.assertEqual(self.store.data['templates'],rows[-3:])
        self.assertFalse((self.store.folder/rows[0]['path']).exists())
        self.assertFalse(orphan.exists())
        self.assertEqual(foreign.read_bytes(),b'keep');self.assertTrue((evidence/'keep.png').exists())
        self.assertEqual(Store(self.store.folder).data['templates'],rows[-3:])

    def test_failed_save_restores_old_sample_and_removes_new_file(self):
        assign(self.catalog,'誤読',self.name,'material',image=plate())
        before=copy.deepcopy(self.store.data);files=set((self.store.folder/'labels').glob('*'))
        with patch.object(self.store,'save',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):assign(self.catalog,'誤読',self.name,'excluded',image=plate('OTHER ITEM'))
        self.assertEqual(self.store.data,before)
        self.assertEqual(set((self.store.folder/'labels').glob('*')),files)

    def test_failed_maintenance_does_not_delete_previous_samples(self):
        rows=self.records(5)
        for row in rows:row['name']=self.name
        self.store.data['templates']=rows
        with patch.object(self.store,'save',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):learning.maintain(self.store)
        self.assertEqual(self.store.data['templates'],rows)
        self.assertTrue(all((self.store.folder/r['path']).is_file() for r in rows))

    def test_deleted_labels_folder_keeps_records_and_can_learn_again(self):
        run=self.store.new_run('アルビ','HD','使用')
        self.store.record(run['id'],[{'name':self.name,'kind':'material'}])
        assign(self.catalog,'誤読',self.name,'material',image=plate())
        stats=self.store.stats(('アルビ','HD','使用'))
        # 削除するのは、このテストの一時Store内の見本フォルダーだけ。
        folder=self.store.folder/'labels'
        self.assertEqual(folder.resolve().parent,self.store.folder.resolve())
        shutil.rmtree(folder)
        store=Store(self.store.folder);vision=Vision(store)
        self.assertTrue(vision.templates)  # 同梱見本は引き続き使える。
        learning.maintain(store)
        self.assertEqual(store.data['templates'],[])
        self.assertEqual(store.stats(('アルビ','HD','使用')),stats)
        self.assertEqual(store.data['overrides'][self.name],'material')
        assign(vision.catalog,'誤読',self.name,'material',image=plate())
        vision.reload()
        self.assertEqual(vision.recognize_template(plate())[0],self.name)
        self.assertEqual(len(list(folder.glob('*.png'))),1)

    def test_missing_folder_still_uses_ocr_and_ignores_corrupt_sample(self):
        vision=Vision(self.store)
        vision.boxes=lambda image,cropped=False:[image]
        with patch.object(vision,'ocr_suggestions',return_value=[self.name]) as ocr:
            result=vision.analyze(plate('UNKNOWN SCREEN'),cropped=True)
        ocr.assert_called_once();self.assertEqual(result['labels'][0]['name'],self.name)
        path=self.store.folder/('labels/'+'d'*20+'.png');path.parent.mkdir();path.write_bytes(b'broken PNG')
        self.store.data['templates']=[{'name':self.name,'kind':'material','path':'labels/'+path.name}]
        vision.reload()  # 壊れた個人用の見本があっても起動を妨げない。

    def test_full_thousand_limit_retires_only_oldest_sample(self):
        self.assertEqual(learning.MAX_SAMPLES,1000)
        rows=self.records(1001)
        self.store.data['templates']=rows;self.store.save()
        learning.maintain(self.store)
        self.assertEqual(self.store.data['templates'],rows[1:])
        self.assertFalse((self.store.folder/rows[0]['path']).exists())
        self.assertTrue((self.store.folder/rows[-1]['path']).is_file())
