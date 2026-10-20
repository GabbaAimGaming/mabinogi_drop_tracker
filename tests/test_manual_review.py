import copy
import json
import tempfile
import queue
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image
from drop_tool.tracker import Store
from drop_tool import manual_review as m
from drop_tool.app import App


class ManualReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name);self.run=self.store.new_run('アルビ','HD','使用')
        self.frame=Image.new('RGB',(80,60),'red')

    def reading(self):
        return {'labels':[{'name':'精製された触媒','raw':'精製された触媒','kind':'material','image':self.frame}]}

    def expected(self):return copy.deepcopy({'rows':self.run['rows'],'status':self.run['status']})

    def test_retake_keeps_one_photo_for_that_run_and_failed_save_preserves_old(self):
        first=m.save_photo(self.store,self.run['id'],self.frame)
        with patch.object(self.store,'save',side_effect=OSError('disk')):
            with self.assertRaises(OSError):m.save_photo(self.store,self.run['id'],self.frame)
        self.assertTrue(first.exists());self.assertEqual(m.photos(self.store,self.run['id']),[first])
        second=m.save_photo(self.store,self.run['id'],self.frame)
        self.assertFalse(first.exists());self.assertTrue(second.exists())
        self.assertEqual(len(list(second.parent.glob('manual-*.png'))),1)

    def test_pending_photo_is_kept_confirmed_photo_removed_but_crops_learning_stay(self):
        photo=m.save_photo(self.store,self.run['id'],self.frame)
        m.replace_reading(self.store,self.run['id'],self.reading(),self.expected())
        crop=self.store.folder/self.run['rows'][0]['image']
        (self.store.folder/'labels').mkdir();learned=self.store.folder/'labels/keep.png';self.frame.save(learned)
        m.cleanup_confirmed(self.store);self.assertTrue(photo.exists())
        self.store.confirm(self.run['id']);m.cleanup_confirmed(self.store)
        self.assertFalse(photo.exists());self.assertTrue(crop.exists());self.assertTrue(learned.exists())

    def test_recapturing_confirmed_run_returns_to_review_before_cleanup(self):
        m.replace_reading(self.store,self.run['id'],self.reading(),self.expected());self.store.confirm(self.run['id'])
        photo=m.save_photo(self.store,self.run['id'],self.frame);m.cleanup_confirmed(self.store)
        self.assertEqual(self.run['status'],'review');self.assertTrue(photo.exists())

    def report(self, folder, kind, run_id):
        p=self.store.folder/'提出用サンプル'/folder;p.mkdir(parents=True)
        self.frame.save(p/'frame-00.png')
        (p/'report.json').write_text(json.dumps({'kind':kind,'run':{'id':run_id},'images':[{'file':'frame-00.png'}]}))
        return p

    def test_cleanup_keeps_explicit_submission_and_other_pending_run(self):
        a=self.report('auto','auto_success',self.run['id'])
        b=self.report('explicit','missed_detection',self.run['id'])
        c=self.report('pending','auto_failure','another-run')
        m.replace_reading(self.store,self.run['id'],self.reading(),self.expected());self.store.confirm(self.run['id'])
        m.cleanup_confirmed(self.store)
        self.assertFalse(a.exists());self.assertTrue((b/'frame-00.png').exists());self.assertTrue((c/'frame-00.png').exists())

    def test_saved_images_never_fall_back_to_another_run_or_global_last_capture(self):
        self.report('wrong','auto_success','another-run')
        self.frame.save(self.store.folder/'last-loot-capture.png')
        self.assertEqual(m.photos(self.store,self.run['id']),[])
        p=self.report('right','auto_success',self.run['id'])
        self.assertEqual(m.photos(self.store,self.run['id']),[p/'frame-00.png'])

    def test_read_replaces_only_target_run_and_never_changes_global_learning(self):
        other=self.store.new_run('アルビ','HD','使用');other_before=copy.deepcopy(other)
        self.store.data['item_links']={'3':'スピリットジェム'}
        self.store.data['overrides']={'スピリットジェム':'excluded'}
        before={k:copy.deepcopy(self.store.data.get(k)) for k in ('item_links','overrides','templates')}
        m.replace_reading(self.store,self.run['id'],self.reading(),self.expected())
        self.assertEqual(self.run['status'],'review');self.assertEqual(other,other_before)
        self.assertEqual([r['name'] for r in self.run['rows']],['精製された触媒'])
        self.assertEqual(before,{k:self.store.data.get(k) for k in before})

    def test_empty_stale_and_failed_save_leave_old_rows_and_images_intact(self):
        m.replace_reading(self.store,self.run['id'],self.reading(),self.expected())
        original=copy.deepcopy(self.run);crop=self.store.folder/self.run['rows'][0]['image']
        with self.assertRaises(ValueError):m.replace_reading(self.store,self.run['id'],{'labels':[]},self.expected())
        stale=self.expected();self.run['status']='confirmed'
        with self.assertRaises(ValueError):m.replace_reading(self.store,self.run['id'],self.reading(),stale)
        self.run['status']=original['status']
        with patch.object(self.store,'save',side_effect=OSError('disk')):
            with self.assertRaises(OSError):m.replace_reading(self.store,self.run['id'],self.reading(),self.expected())
        self.assertEqual(self.run,original);self.assertTrue(crop.exists())
        self.assertEqual(len(list(crop.parent.glob('reread-*.png'))),1)

    def test_three_second_countdown_captures_without_ocr_and_stop_cancels(self):
        for cancel in (False,True):
            app=App.__new__(App);app.busy=False;app.display_id='chosen';app.active_id='other'
            app.hwnd=1;app.epoch=5;app.root=Mock();app.status=Mock();app.stop=Mock();app.submit=Mock()
            pending=[];app.root.after.side_effect=lambda delay,callback:pending.append((delay,callback))
            app.capture_manual()
            self.assertEqual(app.manual_target,'chosen')
            if cancel:app.epoch+=1
            while pending:
                delay,callback=pending.pop(0);self.assertEqual(delay,1000);callback()
            if cancel:app.submit.assert_not_called()
            else:app.submit.assert_called_once_with('manual_photo')

    def test_decline_saved_read_does_not_replace_anything(self):
        app=App.__new__(App);app.root=Mock();app.store=self.store
        with patch('drop_tool.app.messagebox.askyesno',return_value=False),patch.object(m,'replace_reading') as replace:
            app.apply_saved_read(self.reading())
        replace.assert_not_called()

    def test_split_and_remove_are_local_and_persist_without_global_mapping(self):
        self.run['rows']=[{'name':'専用エンチャントスクロール指組み精製された触媒','raw':'original','kind':'review'},
                          {'name':'3','kind':'review'}]
        other=self.store.new_run('アルビ','HD','使用');other['rows']=copy.deepcopy(self.run['rows'])
        other_before=copy.deepcopy(other);before=copy.deepcopy(self.store.data['overrides'])
        m.edit_row(self.store,self.run['id'],0,['専用エンチャントスクロール・指組み','精製された触媒'],'material')
        m.edit_row(self.store,self.run['id'],2,[],'excluded')
        self.assertEqual([r['name'] for r in self.run['rows']],['専用エンチャントスクロール・指組み','精製された触媒'])
        self.assertEqual(other,other_before);self.assertEqual(self.store.data['overrides'],before)
        self.assertFalse(self.store.data.get('item_links'))
        self.store.confirm(self.run['id'])
        reread=Store(self.store.folder);self.assertEqual(reread.find(self.run['id'])['rows'],self.run['rows'])

    def test_local_edit_rejects_invalid_names_and_recovers_from_write_failure(self):
        self.run['rows']=[{'name':'bad','kind':'review'}];original=copy.deepcopy(self.run)
        with patch.object(self.store,'save',side_effect=OSError('disk')):
            with self.assertRaises(OSError):m.edit_row(self.store,self.run['id'],0,['real'],'material')
        self.assertEqual(self.run,original)
        with self.assertRaises(ValueError):m.edit_row(self.store,self.run['id'],0,['x'*161],'material')
        self.store.data['item_links']={'3':'スピリットジェム'}
        with self.assertRaises(ValueError):m.edit_row(self.store,self.run['id'],0,['3'],'material')

    def test_invalid_confirmed_rows_do_not_lose_their_capture(self):
        photo=m.save_photo(self.store,self.run['id'],self.frame)
        self.run.update(status='confirmed',rows=[{'name':'unknown','kind':'review'}])
        m.cleanup_confirmed(self.store);self.assertTrue(photo.exists())

    def worker_app(self):
        app=App.__new__(App);app.busy=False;app.epoch=5;app.hwnd=1
        app.jobs=queue.Queue();app.manual_target='chosen';app.vision=Mock()
        app.grab=Mock(return_value=self.frame);app.ready=Mock(return_value=True)
        return app

    def test_capture_worker_does_not_ocr_or_depend_on_chest_and_keeps_run_id(self):
        app=self.worker_app();app.submit('manual_photo')
        token,mode,result,error=app.jobs.get(timeout=5)
        self.assertEqual((token,mode,error),(5,'manual_photo',None))
        self.assertEqual(result['run_id'],'chosen');self.assertEqual(result['frame'].size,self.frame.size)
        app.vision.analyze.assert_not_called();self.assertEqual(app.ready.call_count,2)

    def test_capture_worker_rejects_background_game(self):
        app=self.worker_app();app.ready.return_value=False;app.submit('manual_photo')
        _,mode,_,error=app.jobs.get(timeout=5)
        self.assertEqual(mode,'manual_photo');self.assertTrue(error)
        app.grab.assert_not_called();app.vision.analyze.assert_not_called()

    def test_saved_read_worker_binds_result_to_original_run_snapshot(self):
        app=self.worker_app();app.saved_read_target=self.run['id'];app.saved_read_expected=self.expected()
        app.vision.analyze.return_value=self.reading();expected=copy.deepcopy(app.saved_read_expected)
        app.submit('saved_read',self.frame)
        _,mode,result,error=app.jobs.get(timeout=5)
        self.assertEqual((mode,error),('saved_read',None))
        self.assertEqual(result['run_id'],self.run['id']);self.assertEqual(result['expected'],expected)
        app.grab.assert_not_called();app.ready.assert_not_called()
