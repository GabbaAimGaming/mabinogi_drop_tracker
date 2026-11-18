"""ネアル廃止後の新規作成と旧記録・CSVの互換性。"""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image
from drop_tool.app import App
from drop_tool.tracker import Store
from drop_tool.exporting import export_statistics
from drop_tool.csv_collection import read_csv
from drop_tool import preflight, read_worker
from drop_tool.config import ROOT
from drop_tool.reward_gate import RewardGate


class NearRetirementTests(unittest.TestCase):
    def test_new_default_and_old_conditions_survive_save_reopen_and_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            old = store.new_run('アルビ', 'HD', '使用')
            store.record(old['id'], [{'name': '精製された触媒', 'kind': 'material'}])
            before = copy.deepcopy(old)
            current = store.new_run('夢幻ラビ', '誘惑')
            self.assertEqual(current['near'], '不使用')
            store.record(current['id'], [{'name': '精製された触媒', 'kind': 'material'}])
            reopened = Store(folder)
            self.assertEqual(reopened.find(old['id']), before)
            self.assertEqual(reopened.find(current['id'])['near'], '不使用')
            reopened.set_player_name('互換確認')
            output = Path(folder) / 'stats.csv'
            export_statistics(reopened, output)
            groups = read_csv(output)
            self.assertEqual({g['near'] for g in groups}, {'使用', '不使用'})
            self.assertEqual(sum(g['count'] for g in groups), 2)

    def test_app_creates_run_without_near_widget_for_any_dungeon(self):
        with tempfile.TemporaryDirectory() as folder:
            app = App.__new__(App)
            app.store = Store(folder)
            app.active_id = None
            app.hwnd = 123
            app.epoch = 0
            app.dungeon = Mock(); app.dungeon.get.return_value = '夢幻ラビ'
            app.difficulty = Mock(); app.difficulty.get.return_value = '誘惑'
            app.stable = Mock(); app.status = Mock(); app.refresh = Mock()
            with patch('drop_tool.app.messagebox.showerror') as error:
                app.new_run()
            error.assert_not_called()
            self.assertTrue(app.watching)
            self.assertEqual(app.store.find(app.active_id)['near'], '不使用')
            self.assertFalse(hasattr(app, 'near'))

    def test_startup_does_not_require_retired_reference_images(self):
        original = Path.is_file
        def exists(path):
            return False if 'near-dialog' in path.parts else original(path)
        with patch.object(Path, 'is_file', exists):
            preflight.check_assets(ROOT)

    def test_observe_and_burst_do_not_call_retired_detector(self):
        app = App.__new__(App)
        app.epoch = 0; app.scan_trace = []; app.reward_gate = RewardGate()
        app.near_detector = Mock()
        app.near_detector.detect.side_effect = AssertionError('retired detector used')
        app.reward_detection = Mock(return_value={'found': False, 'match': None})
        put = Mock(); frame = Image.new('RGB', (100, 100))
        with patch('drop_tool.read_worker.quick_check', return_value=True):
            read_worker._observe(app, put, frame, 0)
            self.assertFalse(put.call_args.args[1]['near_dialog'])
            app.grab = Mock(return_value=frame)
            app.vision = Mock()
            app.vision.analyze.return_value = {'labels': []}
            def collect(grab, visible, first):
                self.assertTrue(visible(first))
                return [first, grab()]
            with patch('drop_tool.read_worker.alt_capture.collect', side_effect=collect), \
                    patch('drop_tool.read_worker.alt_capture.read', return_value={'labels': []}):
                read_worker._burst(app, put, frame, [], {}, epoch=0, hwnd=1, center=False)
        app.near_detector.detect.assert_not_called()
