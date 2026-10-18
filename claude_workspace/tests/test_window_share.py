# Gameplay samples remain private; validated separately before release.
from pathlib import Path as _FixturePath
import unittest as _fixture_unittest
if not (_FixturePath(__file__).resolve().parent / 'fixtures').exists() or not (_FixturePath(__file__).resolve().parents[1] / 'tools/benchmarks/video').exists():
    raise _fixture_unittest.SkipTest('非公開の提供画像を使う回帰テスト（配布前に別環境で検証）')

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
