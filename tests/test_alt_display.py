# Full gameplay samples are private and are not distributed in this repository.
from pathlib import Path as _FixturePath
import unittest as _fixture_unittest
if not (_FixturePath(__file__).resolve().parent / 'fixtures').exists() or not (_FixturePath(__file__).resolve().parents[1] / 'tools/benchmarks/video').exists():
    raise _fixture_unittest.SkipTest('非公開の提供画像を使う回帰テスト（配布前に別環境で検証済み）')

"""録画から確認したALT表示の判定・連写・多数決。キー入力は一切使わない。"""
import tempfile
import unittest
from unittest.mock import Mock

from PIL import Image

from drop_tool import alt_capture
from drop_tool.alt_display import quick_check
from drop_tool.config import ROOT
from drop_tool.tracker import Store, StableReading, consensus
from drop_tool.vision import Vision

VIDEO = ROOT / 'tools' / 'benchmarks' / 'video'


def load(name):
    with Image.open(VIDEO / name) as image:
        return image.convert('RGB')


class RecordedAltDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vision = Vision(Store(tempfile.mkdtemp()))

    def test_name_tags_without_alt_are_not_items(self):
        # v0.15はこの画面の名札を12行の品名として読み、周回に記録できてしまっていた。
        for name in ('video-nametags.png', 'video-after-release.png'):
            self.assertEqual(Vision.boxes(None, load(name), cropped=True), [], name)
            self.assertEqual(self.vision.analyze(load(name), cropped=True)['labels'], [], name)

    def test_alt_display_reads_eight_stacked_plates(self):
        image = load('video-alt-loot.png')
        self.assertTrue(quick_check(image))
        pieces = Vision.boxes(None, image, cropped=True)
        self.assertEqual(len(pieces), 8)
        # 縦に積まれた順（上から）に並び、位置情報を持つ。
        self.assertEqual([p.info['pos'][0] for p in pieces], sorted(p.info['pos'][0] for p in pieces))
        names = [x['name'] for x in self.vision.analyze(image, cropped=True)['labels']]
        for expected in ('炎の糸', 'コンボカード', 'ケルティックロイヤルウォーリアハンマー', 'ケルティックバトルアックス'):
            self.assertIn(expected, names)

    def test_wand_name_is_not_split_by_bright_background(self):
        widths = [p.width for p in Vision.boxes(None, load('video-alt-loot.png'), cropped=True)]
        self.assertNotIn(43, widths)  # 「…ワ｜ンド」の誤分割で出ていた断片


def reading(*rows, registered=()):
    return {'message': '', 'labels': [
        {'name': name, 'kind': 'review', 'pos': (y, 100, 120), 'registered': name in registered,
         'image': Image.new('RGB', (10, 10)), 'fingerprint': f'{name}{y}'}
        for y, name in rows]}


class ConsensusTests(unittest.TestCase):
    def test_majority_name_per_row_and_flicker_is_dropped(self):
        readings = [
            reading((10, 'スビリットジェム'), (28, '炎の糸')),
            reading((11, 'スピリットジェム'), (28, '炎の糸'), (46, 'ト')),
            reading((10, 'スビリットジェム'), (29, '炎の糸')),
        ]
        merged = consensus(readings)
        self.assertEqual([x['name'] for x in merged['labels']], ['スビリットジェム', '炎の糸'])

    def test_tie_prefers_registered_name(self):
        merged = consensus([reading((10, 'スビリットジェム')),
                            reading((10, 'スピリットジェム'), registered={'スピリットジェム'})])
        self.assertEqual(merged['labels'][0]['name'], 'スピリットジェム')

    def test_release_needs_two_readings(self):
        stable = StableReading()
        stable.observe(reading((10, '炎の糸')))
        self.assertIsNone(stable.release())
        stable.observe(reading((10, '炎の糸')))
        stable.observe(reading((11, '炎の糸')))
        self.assertEqual(stable.release()['labels'][0]['name'], '炎の糸')


class BurstCaptureTests(unittest.TestCase):
    def run_collect(self, visible):
        sequence = iter(visible)
        clock = [0.0]
        return alt_capture.collect(lambda: next(sequence), lambda frame: frame,
                                   first=True, clock=lambda: clock[0],
                                   sleep=lambda d: clock.__setitem__(0, clock[0] + d))

    def test_stops_after_display_disappears_twice(self):
        self.assertEqual(len(self.run_collect([True, True, False, True, False, False, True])), 4)

    def test_frame_limit_and_capture_error(self):
        self.assertEqual(len(self.run_collect([True] * 20)), alt_capture.MAX_FRAMES)
        def broken():
            raise ValueError('background')
        self.assertEqual(alt_capture.collect(broken, bool, first='f', sleep=lambda d: None), ['f'])

    def test_pick_spreads_frames(self):
        self.assertEqual(alt_capture.pick(list(range(6))), [0, 2, 3, 5])
        self.assertEqual(alt_capture.pick([1, 2]), [1, 2])

    def test_read_merges_and_reports_empty(self):
        frames = ['a', 'b', 'c']
        analyze = Mock(side_effect=[reading((10, '炎の糸')), reading((10, '炎の糸')), {'labels': []}])
        result = alt_capture.read(analyze, frames)
        self.assertEqual([x['name'] for x in result['labels']], ['炎の糸'])
        self.assertEqual(result['frames'], 3)
        self.assertEqual(alt_capture.read(Mock(return_value={'labels': []}), frames)['labels'], [])

    def test_recorded_frames_end_to_end(self):
        vision = Vision(Store(tempfile.mkdtemp()))
        frames = [load('video-alt-loot.png')] * 3
        result = alt_capture.read(lambda f: vision.analyze(f, cropped=True), frames)
        self.assertEqual(len(result['labels']), 8)


class FinalResultTests(unittest.TestCase):
    def test_final_burst_result_is_saved_once(self):
        import queue
        from drop_tool.app import App
        app = App.__new__(App)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        app.store = Store(temp.name)
        app.root = Mock(); app.status = Mock(); app.diagnostic = Mock(); app.refresh = Mock()
        app.epoch = 0; app.busy = False; app.hwnd = 1; app.stable = StableReading()
        app.jobs = queue.Queue(); app.completion_sound = Mock(); app.watching = True; app.share = None
        app.submit = Mock()
        run = app.store.new_run('アルビ', 'HD', '使用')
        app.active_id = run['id']
        result = reading((10, '炎の糸'))
        result['final'] = True
        app.jobs.put((0, 'live', result, None))
        from unittest.mock import patch
        with patch('drop_tool.app.capture.active', return_value=True):
            app.poll()
        self.assertEqual(run['status'], 'review')
        self.assertEqual([r['name'] for r in run['rows']], ['炎の糸'])
        self.assertFalse(app.watching)
        app.submit.assert_not_called()
        # 解析完了（多数決で確定・保存）の時点で完了音を1回鳴らす。
        app.completion_sound.play.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()


class CaptureSoundTests(unittest.TestCase):
    def make_app(self):
        import queue
        from drop_tool.app import App
        app = App.__new__(App)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        app.store = Store(temp.name)
        app.root = Mock(); app.status = Mock(); app.diagnostic = Mock(); app.refresh = Mock()
        app.epoch = 0; app.busy = True; app.hwnd = 1; app.stable = StableReading()
        app.jobs = queue.Queue(); app.completion_sound = Mock(); app.watching = True; app.share = None
        app.read_attempts = 0; app.worker_phase = ''; app.worker_started = 0
        return app

    def test_capture_event_plays_short_sound_without_ending_work(self):
        app = self.make_app()
        app.jobs.put((0, 'captured', {'frames': 6}, None))
        app.jobs.put((-1, 'captured', {'frames': 6}, None))  # 停止前の古い通知は鳴らさない
        app.poll()
        app.completion_sound.play.assert_called_once_with(kind='captured')
        self.assertTrue(app.busy)  # 解析中のワーカーは継続
        self.assertIn('ALTを離して構いません', app.status.set.call_args.args[0])

    def test_sound_files_exist_and_are_selected_by_kind(self):
        from unittest.mock import patch
        from drop_tool.notification import CompletionSound, SOUNDS
        for name in SOUNDS.values():
            self.assertTrue((ROOT / 'assets' / name).is_file(), name)
        with tempfile.TemporaryDirectory() as folder, \
                patch('drop_tool.notification.winsound.PlaySound') as play:
            from pathlib import Path
            sound = CompletionSound(Path(folder))
            sound.play(kind='captured')
            sound.play()
        self.assertTrue(play.call_args_list[0].args[0].endswith('capture-complete.wav'))
        self.assertTrue(play.call_args_list[1].args[0].endswith('read-complete.wav'))

    def test_burst_reports_capture_before_result(self):
        from unittest.mock import patch
        from drop_tool.vision import CENTER
        app = self.make_app()
        app.busy = False
        app.settings = {'scan_mode': 'center'}
        app.vision = Mock()
        app.vision.analyze.return_value = reading((10, '炎の糸'))
        image = load('video-alt-loot.png')
        app.chest_detector = Mock()
        app.chest_detector.detect.return_value = {'found':True,'match':None}
        app.reward_gate = Mock()
        app.reward_gate.observe.return_value = True
        app.reward_gate.elapsed.return_value = 3
        app.scan_trace = []
        with patch.object(app, 'grab', return_value=image):
            app.submit('live')
            first = app.jobs.get(timeout=10)
            second = app.jobs.get(timeout=10)
        self.assertEqual(first[1], 'start')
        self.assertFalse(first[2]['manual'])
        self.assertTrue(second[2]['final'])
