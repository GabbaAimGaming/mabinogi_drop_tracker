import queue
import tempfile
import unittest
from unittest.mock import Mock,patch
from app import App
from tracker import Store, StableReading
from windows_capture import game_window

class CaptureFlowTests(unittest.TestCase):
    def test_auto_select_game_not_browser_or_tool(self):
        found=[(1,'マビノギ - Google Chrome'),(2,'マビノギ交易'),(3,'マビノギ')]
        self.assertEqual(game_window(found),3)
        self.assertIsNone(game_window(found[:2]))
        self.assertEqual(game_window([(3,'マビノギ'),(4,'Mabinogi')],4),4)

    def test_delete_removes_records_and_stats_but_preserves_learning(self):
        app=self.make_app();store=app.store
        a=store.new_run('アルビ','HD','使用');b=store.new_run('アルビ','HD','使用')
        store.record(a['id'],[{'name':'素材','kind':'material','image':''}])
        store.data['overrides']['素材']='material';store.save()
        self.assertEqual(store.delete_runs([a['id']]),1)
        reloaded=Store(store.folder)
        self.assertEqual([r['id'] for r in reloaded.data['runs']],[b['id']])
        self.assertEqual(reloaded.stats(('アルビ','HD','使用')),(0,1,[]))
        self.assertEqual(reloaded.data['overrides'],{'素材':'material'})
        self.assertEqual(store.delete_runs([b['id']]),1)
        self.assertEqual(Store(store.folder).data['runs'],[])

    def test_failed_delete_retains_memory_records(self):
        store=self.make_app().store
        run=store.new_run('アルビ','HD','使用')
        store.save=Mock(side_effect=OSError('disk error'))
        with self.assertRaises(OSError):store.delete_runs([run['id']])
        self.assertEqual(store.find(run['id']),run)

    def make_app(self):
        app=App.__new__(App)
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        app.store=Store(temp.name);app.root=Mock();app.status=Mock()
        app.epoch=0;app.busy=False;app.hwnd=123;app.stable=StableReading()
        app.jobs=queue.Queue()
        app.completion_sound=Mock();app.active_id=None;app.watching=False;app.refresh=Mock()
        app.worker_phase='';app.worker_started=0;app.last_diagnostic='';app.read_attempts=0;app.diagnostic=Mock()
        return app


    def test_timed_read_bypasses_alt_key_gate_and_chest(self):
        app=self.make_app();app.submit=Mock()
        app.active_id=app.store.new_run('アルビ','HD','使用')['id']
        with patch('app.capture.user32.GetAsyncKeyState',side_effect=AssertionError('must not require ALT API')):
            app.timed_read()
            for _ in range(5):app.root.after.call_args.args[1]()
        app.submit.assert_called_once_with('manual')

    def test_label_stability_does_not_need_chest(self):
        stable=StableReading();result={'labels':[{'name':'素材','kind':'material'}]}
        for _ in range(3):stable.observe(result)
        self.assertIs(stable.finish(),result)



    def test_capture_error_does_not_stop_polling(self):
        app=self.make_app();app.jobs.put((0,'live',None,'game not foreground'))
        app.poll()
        self.assertIn('game not foreground',app.status.set.call_args.args[0])
        app.root.after.assert_called_with(150,app.poll)

    def test_capture_runs_without_key_api_and_stops_when_background(self):
        app = self.make_app()
        app.watching = True
        app.active_id = app.store.new_run('アルビ', 'HD', '使用')['id']
        app.submit = Mock()
        with patch('app.capture.active', return_value=False):
            app.tick()
        app.submit.assert_not_called()
        self.assertIn('手前', app.diagnostic.set.call_args.args[0])
        with patch('app.capture.active', return_value=True), patch(
            'app.capture.user32.GetAsyncKeyState', side_effect=AssertionError('key API forbidden')
        ):
            app.tick()
        app.submit.assert_called_once_with('live')

    def test_stable_screen_saved_once_without_key_release_and_needs_confirmation(self):
        from PIL import Image
        app = self.make_app()
        app.watching = True
        run = app.store.new_run('アルビ', 'HD', '使用')
        app.active_id = run['id']
        result = {'message': '1行', 'labels': [
            {'name': '素材', 'kind': 'material', 'image': Image.new('RGB', (40, 10))}
        ]}
        with patch('app.capture.active', return_value=True), patch(
            'app.capture.user32.GetAsyncKeyState', side_effect=AssertionError('key API forbidden')
        ):
            for index in range(3):
                app.jobs.put((0, 'live', result, None))
                app.poll()
                self.assertEqual(run['status'], 'waiting' if index < 2 else 'review')
        self.assertFalse(app.watching)
        self.assertEqual(app.store.stats(('アルビ', 'HD', '使用'))[0], 0)
        self.assertEqual(run['rows'][0]['kind'], 'material')
        app.store.confirm(run['id'])
        self.assertEqual(app.store.stats(('アルビ', 'HD', '使用'))[0], 1)
        app.submit = Mock()
        app.tick()
        app.submit.assert_not_called()

    def test_stale_and_background_results_cannot_record(self):
        app = self.make_app()
        app.watching = True
        app.active_id = app.store.new_run('アルビ', 'HD', '使用')['id']
        result = {'message': '1行', 'labels': [{'name': '素材', 'kind': 'material'}]}
        for _ in range(3):
            app.jobs.put((-1, 'live', result, None))
        app.poll()
        with patch('app.capture.active', return_value=False):
            for _ in range(3):
                app.jobs.put((0, 'live', result, None))
            app.poll()
        self.assertIsNone(app.stable.finish())
        self.assertEqual(app.store.find(app.active_id)['status'], 'waiting')

    def test_failed_record_can_retry_without_losing_waiting_state(self):
        app = self.make_app()
        run = app.store.new_run('アルビ', 'HD', '使用')
        with patch.object(app.store, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                app.store.record(run['id'], [{'name': '素材', 'kind': 'material'}], require_review=True)
        self.assertEqual(run['status'], 'waiting')
        self.assertEqual(run['rows'], [])
        self.assertEqual(Store(app.store.folder).find(run['id'])['status'], 'waiting')

if __name__=='__main__':unittest.main()
