import tempfile
import unittest
from PIL import Image,ImageDraw
from tracker import Store,StableReading,default_near,ROOT,Rules
from vision import Vision

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name)
    def rows(self,*names):return [{'name':n,'raw':n,'kind':Rules().classify(n),'image':''} for n in names]
    def test_albi_default_not_applied_to_other_dungeons(self):
        self.assertEqual(default_near('アルビ','HD'),'使用')
        self.assertEqual(default_near('夢幻ラビ','誘惑'),'未指定')
        r=self.store.new_run('アルビ','HD','不使用');self.assertEqual(r['near'],'不使用')
    def test_same_run_is_never_counted_twice_identical_next_run_is_counted(self):
        a=self.store.new_run('アルビ','HD','使用');rows=self.rows('マナハーブ')
        self.assertTrue(self.store.record(a['id'],rows));self.assertFalse(self.store.record(a['id'],rows))
        b=self.store.new_run('アルビ','HD','使用');self.store.record(b['id'],rows)
        self.assertEqual(self.store.stats(('アルビ','HD','使用')),(2,0,[('マナハーブ',2,1.)]))
    def test_excluded_only_run_is_in_denominator_unknown_is_pending(self):
        for names in [('マナハーブ',),('金貨','炎の糸','スピリットジェム(500)'),('新しい素材',)]:
            r=self.store.new_run('アルビ','HD','使用');self.store.record(r['id'],self.rows(*names))
        self.assertEqual(self.store.stats(('アルビ','HD','使用')),(2,1,[('マナハーブ',1,.5)]))
    def test_missing_run_is_not_zero_and_conditions_are_separate(self):
        self.store.new_run('アルビ','HD','使用')
        r=self.store.new_run('アルビ','HD','不使用');self.store.record(r['id'],self.rows('マナハーブ'))
        self.assertEqual(self.store.stats(('アルビ','HD','使用')),(0,1,[]))
        self.assertEqual(self.store.stats(('アルビ','HD','不使用'))[0],1)
    def test_reopen_preserves_records_and_creates_backup(self):
        r=self.store.new_run('アルビ','HD','使用');self.store.record(r['id'],self.rows('マナハーブ'))
        other=Store(self.tmp.name)
        self.assertEqual(other.stats(('アルビ','HD','使用'))[0],1)
        self.assertTrue(list((other.folder/'backups').glob('*.json')))
    def test_unknown_needs_resolution_before_confirmation(self):
        r=self.store.new_run('アルビ','HD','使用');self.store.record(r['id'],self.rows('誤読'))
        with self.assertRaises(ValueError):self.store.confirm(r['id'])
        r['rows'][0].update(name='マナハーブ',kind='material');self.store.confirm(r['id'])
        self.assertEqual(self.store.stats(('アルビ','HD','使用'))[0],1)
    def test_empty_capture_cannot_be_confirmed(self):
        r=self.store.new_run('アルビ','HD','使用')
        with self.assertRaises(ValueError):self.store.record(r['id'],[])
        with self.assertRaises(ValueError):self.store.confirm(r['id'])
    def test_materials_do_not_match_equipment_substrings(self):
        rule=Rules()
        self.assertEqual(rule.classify('古いソード'),'excluded')
        self.assertEqual(rule.classify('古いソードの破片'),'review')
        self.assertEqual(rule.classify('炎の糸'), 'excluded')
    def test_stability_and_finish(self):
        stable=StableReading();result={'labels':[{'name':'マナハーブ','kind':'material'}]}
        self.assertFalse(stable.observe(result));self.assertFalse(stable.observe(result));self.assertTrue(stable.observe(result))
        self.assertIs(stable.finish(),result);self.assertIsNone(stable.finish())
        for i in range(3):stable.observe(result)
        stable.observe({'labels':[]});self.assertIsNone(stable.finish())
    def test_supplied_screen_excludes_equipment_and_keeps_five_materials(self):
        v=Vision(self.store)
        # Only the Ctrl+F HUD is unknown in this supplied fixture; the actual
        # game's Japanese OCR path is tested separately during packaging.
        v.ocr_suggestions=lambda imgs:['Ctrl+F']*len(imgs)
        result=v.analyze(Image.open(ROOT/'references/albi-hd-near.png'))
        self.assertEqual(len(result['labels']),13)
        self.assertEqual({r['name'] for r in result['labels'] if r['kind']=='material'},
            {'マナハーブ','光を失った金属の破片','歪曲の粉','封印の黒い金属','悪夢の番人の遺物'})
        self.assertEqual(sum(r['kind']=='excluded' for r in result['labels']),8)
    def test_labels_work_without_chest_and_blank_frame_is_rejected(self):
        v=Vision(self.store)
        v.ocr_suggestions=lambda imgs:['Ctrl+F']*len(imgs)
        self.assertFalse(v.analyze(Image.new('RGB',(1920,1080),'black'))['labels'])
        im=Image.open(ROOT/'references/albi-hd-near.png').convert('RGB')
        ImageDraw.Draw(im).rectangle((1130,280,1200,335),fill=(120,80,60))
        self.assertEqual(len(v.analyze(im)['labels']),13)
    def test_manual_label_learning_survives_restart(self):
        v=Vision(self.store);im=Image.new('RGB',(120,20),'black');ImageDraw.Draw(im).text((3,3),'NEW MATERIAL',fill='white')
        v.learn('追加素材','material',im)
        other=Vision(Store(self.tmp.name));self.assertEqual(other.recognize_template(im),('追加素材','material'))
    def test_user_exclusion_overrides_bundled_material(self):
        v=Vision(self.store);im=Image.open(ROOT/'references/labels/00.png').convert('RGB')
        v.learn('マナハーブ','excluded',im)
        self.assertEqual(v.recognize_template(im),('マナハーブ','excluded'))
        self.assertEqual(Vision(Store(self.tmp.name)).recognize_template(im),('マナハーブ','excluded'))

if __name__=='__main__':unittest.main()
