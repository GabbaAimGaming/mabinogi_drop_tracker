"""長期利用でディスク・CPU・メモリーが増え続けないことを確認する。"""
import json
import os
import queue
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np
from PIL import Image, ImageDraw

from drop_tool import retention
from drop_tool.csv_collection import CsvCollection
from drop_tool.tracker import Store, StableReading
from drop_tool.vision import Vision


def label(text_width, seed=0):
    """黒地に白い文字風の帯を描いた品名画像。"""
    image = Image.new('RGB', (text_width + 8, 18), (10, 10, 10))
    draw = ImageDraw.Draw(image)
    for i in range(0, text_width, 6):
        if (i // 6 + seed) % 3:
            draw.rectangle((4 + i, 4, 7 + i, 13), fill=(240, 240, 240))
    return image


class BackupRotationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_records_backups_are_capped_and_latest_kept(self):
        store = Store(self.temp.name)
        for i in range(80):
            store.new_run('アルビ', 'HD', '使用')
        before = store.path.read_bytes()
        store.new_run('アルビ', 'HD', '使用')
        backups = list((store.folder / 'backups').glob('*.json'))
        self.assertLessEqual(len(backups), retention.JSON_BACKUP_KEEP)
        self.assertEqual(retention.latest_backup(store.folder / 'backups').read_bytes(), before)

    def test_csv_backups_are_capped_and_not_mixed_with_records(self):
        store = Store(self.temp.name)
        for _ in range(3):
            store.new_run('アルビ', 'HD', '使用')
        record_backups = set((store.folder / 'backups').glob('*.json'))
        collection = CsvCollection(self.temp.name)
        for i in range(25):
            collection.replace([dict(player=f'p{i}', dungeon='アルビ', difficulty='HD', near='使用',
                                     count=1, pending=0, items={})])
        self.assertLessEqual(len(list((store.folder / 'backups').glob('csv-*.json'))), 10)
        self.assertTrue(record_backups.issubset(set((store.folder / 'backups').glob('*.json'))))

    def test_same_content_backup_is_refreshed_not_deleted(self):
        folder = Path(self.temp.name)
        source = folder / 'a.json'
        source.write_text('{"x": 1}', 'utf-8')
        first = retention.backup_json(source, folder / 'b', keep=2)
        old = time.time() - 100
        os.utime(first, (old, old))
        for n in range(2, 4):
            source.write_text(json.dumps({'x': n}), 'utf-8')
            retention.backup_json(source, folder / 'b', keep=2)
        source.write_text('{"x": 1}', 'utf-8')
        self.assertEqual(retention.backup_json(source, folder / 'b', keep=2), first)
        self.assertTrue(first.exists())
        self.assertEqual(retention.latest_backup(folder / 'b'), first)


class LogRotationTests(unittest.TestCase):
    def test_log_rotates_one_generation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'errors.log'
            for _ in range(50):
                retention.append_log(path, 'x' * 100 + '\n', limit=1000)
            self.assertLessEqual(path.stat().st_size, 1000 + 101)
            self.assertTrue((Path(folder) / 'errors.log.1').exists())
            self.assertEqual(len(list(Path(folder).glob('errors.log*'))), 2)


class LiveCaptureWriteTests(unittest.TestCase):
    def make_app(self):
        from drop_tool.app import App
        app = App.__new__(App)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        app.store = Store(temp.name)
        app.root = Mock(); app.status = Mock(); app.diagnostic = Mock()
        app.epoch = 0; app.busy = False; app.hwnd = 1; app.stable = StableReading()
        app.jobs = queue.Queue(); app.completion_sound = Mock(); app.refresh = Mock()
        app.active_id = None; app.watching = True
        app.worker_phase = ''; app.worker_started = 0; app.last_diagnostic = ''; app.read_attempts = 0
        app.vision = Mock()
        return app

    def test_live_frames_are_not_written_every_tick(self):
        app = self.make_app()
        crop = Image.new('RGB', (40, 10))
        app.vision.analyze.return_value = {'message': '1行', 'labels': [
            {'name': '素材', 'kind': 'material', 'image': crop}]}
        frame = Image.new('RGB', (320, 200), 'gray')
        app.submit('live', frame)
        epoch, mode, result, error = app.jobs.get(timeout=10)
        self.assertIsNone(error)
        self.assertFalse((app.store.folder / 'last-loot-capture.png').exists())
        self.assertIs(result['frame'], frame)

    def test_failed_attempt_keeps_frame_in_memory_for_report(self):
        app = self.make_app()
        app.vision.analyze.return_value = {'message': 'なし', 'labels': []}
        app.submit('live', Image.new('RGB', (320, 200)))
        result = app.jobs.get(timeout=10)[2]
        self.assertEqual(len(result['sample_frames']), 1)
        self.assertFalse((app.store.folder / 'last-loot-capture.png').exists())

    def test_stable_reading_writes_capture_once(self):
        app = self.make_app()
        app.active_id = app.store.new_run('アルビ', 'HD', '使用')['id']
        frame = Image.new('RGB', (320, 200), 'gray')
        result = {'message': '1行', 'frame': frame, 'labels': [
            {'name': '素材', 'kind': 'material', 'image': Image.new('RGB', (40, 10))}]}
        app.save_live_reading(result)
        target = app.store.folder / 'last-loot-capture.png'
        for _ in range(100):
            if target.exists():
                break
            time.sleep(0.05)
        self.assertTrue(target.exists())
        self.assertNotIn('frame', result)


class TemplateGrowthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.vision = Vision(self.store)

    def test_templates_keep_masks_not_images(self):
        self.assertTrue(all(isinstance(t[2], np.ndarray) for t in self.vision.templates))

    def test_relearning_same_label_does_not_grow_records(self):
        image = label(120)
        for name in ('誤読A', '誤読B', '正式名'):
            self.vision.learn(name, 'material', image)
        self.assertEqual([r['name'] for r in self.store.data['templates']], ['正式名'])
        self.assertEqual(self.vision.recognize_template(image), ('正式名', 'material'))

    def test_different_labels_are_all_kept(self):
        self.vision.learn('素材A', 'material', label(120, 0))
        self.vision.learn('素材B', 'material', label(60, 1))
        self.assertEqual(sorted(r['name'] for r in self.store.data['templates']), ['素材A', '素材B'])


if __name__ == '__main__':
    unittest.main()
