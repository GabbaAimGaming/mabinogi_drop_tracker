# Full gameplay samples are private and are not distributed in this repository.
from pathlib import Path as _FixturePath
import unittest as _fixture_unittest
if not (_FixturePath(__file__).resolve().parent / 'fixtures').exists() or not (_FixturePath(__file__).resolve().parents[1] / 'tools/benchmarks/video').exists():
    raise _fixture_unittest.SkipTest('非公開の提供画像を使う回帰テスト（配布前に別環境で検証済み）')

"""画面共有（ウィンドウ指定キャプチャ）と中央スキャン。Windows APIは偽物で置き換える。"""
import queue
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image, ImageFilter

from drop_tool import settings
from drop_tool.config import ROOT
from drop_tool.tracker import Store, StableReading
from drop_tool.vision import CENTER, Vision, label_presence
from drop_tool.window_share import ShareUnavailable, WindowShare


class FakeFrame:
    def __init__(self, rgb):
        h, w = rgb.shape[:2]
        bgra = np.zeros((h, w, 4), np.uint8)
        bgra[:, :, :3] = rgb[:, :, ::-1]
        bgra[:, :, 3] = 255
        self.frame_buffer, self.width, self.height = bgra, w, h


class FakeCapture:
    """windows-capture の WindowsCapture と同じ呼び出し形。"""
    instances = []
    fail = None

    def __init__(self, **kwargs):
        if FakeCapture.fail:
            raise FakeCapture.fail
        self.kwargs = kwargs
        self.handlers = {}
        self.control = Mock()
        FakeCapture.instances.append(self)

    def event(self, handler):
        self.handlers[handler.__name__] = handler
        return handler

    def start_free_threaded(self):
        return self.control

    def push(self, rgb):
        self.handlers['on_frame_arrived'](FakeFrame(rgb), Mock())


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def gradient(w=200, h=100):
    x = np.tile(np.arange(w, dtype=np.uint8), (h, 1))
    return np.dstack([x, np.full((h, w), 50, np.uint8), np.full((h, w), 200, np.uint8)])


class WindowShareTests(unittest.TestCase):
    def setUp(self):
        FakeCapture.instances = []
        FakeCapture.fail = None
        self.clock = Clock()
        self.share = WindowShare(42, 'マビノギ', backend=FakeCapture, clock=self.clock,
                                 offset=lambda hwnd, w, h: (10, 20, w - 10, h)).start()
        self.capture = FakeCapture.instances[-1]

    def test_targets_the_selected_window_without_cursor(self):
        self.assertEqual(self.capture.kwargs['window_hwnd'], 42)
        self.assertFalse(self.capture.kwargs['cursor_capture'])
        self.assertTrue(self.share.running)

    def test_frame_is_rgb_and_cropped_to_client_area(self):
        rgb = gradient()
        self.capture.push(rgb)
        image = self.share.frame()
        self.assertEqual(image.size, (180, 80))
        self.assertEqual(image.getpixel((0, 0)), tuple(int(v) for v in rgb[20, 10]))

    def test_region_is_relative_to_client_area(self):
        self.capture.push(gradient())
        image = self.share.frame(CENTER)
        self.assertEqual(image.size, (round(180 * CENTER[2]) - round(180 * CENTER[0]),
                                      round(80 * CENTER[3]) - round(80 * CENTER[1])))

    def test_buffer_is_copied_and_frames_are_throttled(self):
        rgb = gradient()
        frame = FakeFrame(rgb)
        self.capture.handlers['on_frame_arrived'](frame, Mock())
        frame.frame_buffer[:] = 0  # ライブラリ側がバッファを再利用しても影響しない
        self.assertNotEqual(self.share.frame().getpixel((50, 10)), (0, 0, 0))
        self.capture.push(np.zeros_like(rgb))
        self.assertEqual(self.share.frames, 1)  # 0.2秒以内の次フレームは捨てる
        self.clock.now += 0.3
        self.capture.push(np.zeros_like(rgb))
        self.assertEqual(self.share.frames, 2)

    def test_missing_stale_and_closed_are_reported(self):
        with self.assertRaises(ShareUnavailable):
            self.share.frame()
        self.capture.push(gradient())
        self.clock.now += 5
        with self.assertRaises(ShareUnavailable):
            self.share.frame()
        self.capture.handlers['on_closed']()
        self.assertFalse(self.share.running)
        with self.assertRaises(ShareUnavailable):
            self.share.frame()

    def test_stop_releases_session(self):
        self.capture.push(gradient())
        self.share.stop()
        self.capture.control.stop.assert_called_once()
        self.assertFalse(self.share.running)

    def test_backend_failure_becomes_share_unavailable(self):
        FakeCapture.fail = RuntimeError('unsupported window')
        with self.assertRaises(ShareUnavailable):
            WindowShare(7, backend=FakeCapture).start()


class SettingsFileTests(unittest.TestCase):
    def test_share_and_scan_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(settings.load(folder)['window_share'])
            self.assertEqual(settings.load(folder)['scan_mode'], 'full')
            saved = settings.save(folder, window_share=True, scan_mode='center')
            self.assertTrue(saved['window_share'])
            self.assertEqual(saved['evidence_keep_runs'], 3)
            with self.assertRaises(ValueError):
                settings.save(folder, scan_mode='alt-key')
            (Path(folder) / 'settings.json').write_text('{"scan_mode": 5}', 'utf-8')
            self.assertEqual(settings.load(folder)['scan_mode'], 'full')


def center(image):
    w, h = image.size
    return image.crop((round(w * CENTER[0]), round(h * CENTER[1]), round(w * CENTER[2]), round(h * CENTER[3])))


class CenterScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full = Image.open(ROOT / 'tests/fixtures/albi-hd-near.png').convert('RGB')
        blank = cls.full.copy()
        w, h = cls.full.size
        box = (round(w * CENTER[0]) - 5, round(h * CENTER[1]) - 5, round(w * CENTER[2]) + 5, round(h * CENTER[3]) + 5)
        blank.paste(cls.full.crop(box).filter(ImageFilter.GaussianBlur(6)), box[:2])
        cls.blank = blank

    def test_presence_detects_labels_and_ignores_empty_center(self):
        self.assertGreater(label_presence(center(self.full)), 0)
        self.assertEqual(label_presence(center(self.blank)), 0)

    def test_presence_never_misses_what_full_detection_finds(self):
        vision = Vision(Store(tempfile.mkdtemp()))
        for name in ('scroll-loot.png', 'adjacent-loot.png', 'overlapping-loot.png'):
            image = Image.open(ROOT / 'tests/fixtures' / name).convert('RGB')
            if vision.boxes(image, cropped=True):
                self.assertGreater(label_presence(image), 0, name)

    def test_cropped_analysis_matches_full_frame(self):
        vision = Vision(Store(tempfile.mkdtemp()))
        full = [x['name'] for x in vision.analyze(self.full)['labels']]
        cropped = [x['name'] for x in vision.analyze(center(self.full), cropped=True)['labels']]
        self.assertEqual(full, cropped)


class AppShareAndScanTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(self.close)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        FakeCapture.instances = []
        FakeCapture.fail = None
        from drop_tool import app as app_module
        self.module = app_module
        real = app_module.WindowShare
        patcher = patch.object(app_module, 'WindowShare',
                               side_effect=lambda hwnd, name='': real(hwnd, name, backend=FakeCapture,
                                                                      offset=lambda h, w, ht: (0, 0, w, ht)))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = app_module.App(self.root, Store(self.temp.name))
        self.app.windows = [(42, 'マビノギ')]
        self.app.hwnd = 42
        self.root.update()

    def close(self):
        self.app.stop_share()
        for job in self.root.tk.call('after', 'info'):
            self.root.after_cancel(job)
        self.root.destroy()

    def test_ui_toggle_starts_and_stops_share_and_persists(self):
        self.app.share_enabled.set(True)
        self.app.toggle_share()
        self.assertTrue(self.app.sharing(42))
        self.assertIn('共有中', self.app.share_state.get())
        self.assertTrue(settings.load(self.temp.name)['window_share'])
        FakeCapture.instances[-1].push(gradient(400, 300))
        with patch.object(self.module.capture, 'capture', side_effect=AssertionError('GDI not used')):
            self.assertEqual(self.app.grab(42).size, (400, 300))
        with patch.object(self.module.capture, 'visible', return_value=True), \
                patch.object(self.module.capture, 'active', return_value=False):
            self.assertTrue(self.app.ready(42))  # 背面でも共有映像なら撮影できる
        session = FakeCapture.instances[-1]
        self.app.share_enabled.set(False)
        self.app.toggle_share()
        session.control.stop.assert_called_once()
        self.assertIsNone(self.app.share)
        self.assertFalse(settings.load(self.temp.name)['window_share'])

    def test_main_bar_and_settings_tab_share_one_switch(self):
        texts = []

        def walk(widget):
            for child in widget.winfo_children():
                if child.winfo_class() == 'TCheckbutton':
                    texts.append((child.cget('text'), str(child.cget('variable'))))
                walk(child)
        walk(self.root)
        share = [v for t, v in texts if '画面共有' in t]
        self.assertEqual(len(share), 2)
        self.assertEqual(len(set(share)), 1)

    def test_unavailable_share_falls_back_to_foreground_capture(self):
        FakeCapture.fail = RuntimeError('Windows 10 1809')
        self.app.share_enabled.set(True)
        self.app.toggle_share()
        self.assertIsNone(self.app.share)
        self.assertIn('利用不可', self.app.share_state.get())
        frame = Image.new('RGB', (10, 10))
        with patch.object(self.module.capture, 'capture', return_value=frame) as gdi:
            self.assertIs(self.app.grab(42), frame)
        gdi.assert_called_once_with(42)

    def test_closed_window_stops_share(self):
        self.app.share_enabled.set(True)
        self.app.toggle_share()
        FakeCapture.instances[-1].handlers['on_closed']()
        self.app.tick()
        self.assertIsNone(self.app.share)
        self.assertIn('閉じられました', self.app.share_state.get())

    def test_scan_mode_is_saved_and_speeds_up_tick(self):
        self.app.scan_mode.set('center')
        self.app.change_scan_mode()
        self.assertEqual(settings.load(self.temp.name)['scan_mode'], 'center')
        with patch.object(self.root, 'after') as after:
            self.app.tick()
        after.assert_called_with(350, self.app.tick)


def final_job(app):
    """撮影完了の途中通知（captured）を読み飛ばし、解析結果を返す。"""
    while True:
        job = app.jobs.get(timeout=10)
        if job[1] not in ('captured','start'):
            return job


class CenterSubmitTests(unittest.TestCase):
    def make_app(self, mode):
        from drop_tool.app import App
        app = App.__new__(App)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        app.store = Store(temp.name)
        app.settings = settings.load(temp.name) | {'scan_mode': mode}
        app.share = None
        app.root = Mock(); app.status = Mock(); app.diagnostic = Mock()
        app.epoch = 0; app.busy = False; app.hwnd = 1; app.stable = StableReading()
        app.jobs = queue.Queue(); app.completion_sound = Mock(); app.refresh = Mock()
        app.active_id = None; app.watching = True
        app.worker_phase = ''; app.worker_started = 0; app.last_diagnostic = ''; app.read_attempts = 0
        app.vision = Mock()
        app.chest_detector = Mock()
        app.chest_detector.detect.return_value = {'found':False,'match':None}
        app.reward_gate = Mock()
        app.reward_gate.observe.return_value = False
        app.reward_gate.elapsed.return_value = 0
        app.reward_gate.chest_until = 0
        app.scan_trace = []
        app.vision.analyze.return_value = {'message': '1行', 'labels': []}
        return app

    def test_center_mode_captures_whole_window_for_chest_and_skips_empty_frames(self):
        app = self.make_app('center')
        empty = Image.new('RGB', (600, 400), (120, 120, 120))
        with patch.object(app, 'grab', return_value=empty) as grab:
            app.submit('live')
            result = final_job(app)[2]
        grab.assert_called_once_with(1)
        app.vision.analyze.assert_not_called()
        self.assertFalse(result['alt'])

    def test_center_mode_reads_when_labels_are_visible(self):
        app = self.make_app('center')
        full = Image.open(ROOT / 'tests/fixtures/albi-hd-near.png').convert('RGB')
        app.reward_gate.observe.return_value = True
        with patch.object(app, 'grab', return_value=full):
            app.submit('live')
            final_job(app)
        self.assertTrue(app.vision.analyze.call_args.kwargs.get('cropped'))

    def test_full_mode_and_manual_read_use_whole_window(self):
        for mode, submit, analyzed in (('full', 'live', 0), ('center', 'manual', 1)):
            app = self.make_app(mode)
            app.active_id = app.store.new_run('アルビ', 'HD', '使用')['id']
            with patch.object(app, 'grab', return_value=Image.new('RGB', (60, 40))) as grab:
                app.submit(submit)
                final_job(app)
            grab.assert_called_once_with(1)
            # 自動監視は品名板が無ければ解析しない。5秒後読取は必ず解析する。
            self.assertEqual(app.vision.analyze.call_count, analyzed)

if __name__ == '__main__':
    unittest.main()
