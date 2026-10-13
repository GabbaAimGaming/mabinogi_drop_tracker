"""名義付きCSV、旧データの引き継ぎ、表示の画素保存を確認する。"""
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from PIL import Image
from drop_tool.tracker import Store
from drop_tool.exporting import export_statistics, CSV_COLUMNS
from drop_tool.image_display import pixel_preview


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)

    def test_old_records_and_learning_survive_name_registration(self):
        run = self.store.new_run('アルビ', 'HD', '使用')
        self.store.data['overrides']['素材'] = 'material'
        self.store.save()
        before = self.store.path.read_bytes()
        self.assertEqual(Store(self.temp.name).player_name, '')
        self.store.set_player_name('  プレイヤーA  ')
        reopened = Store(self.temp.name)
        self.assertEqual(reopened.player_name, 'プレイヤーA')
        self.assertEqual(reopened.data['runs'], [run])
        self.assertEqual(reopened.data['overrides'], {'素材': 'material'})
        self.assertTrue(any(p.read_bytes() == before for p in (reopened.folder/'backups').glob('*')))

    def test_csv_contains_name_and_same_statistics(self):
        self.store.set_player_name('A,"名前"')
        for name in ('素材', '別の素材'):
            run = self.store.new_run('アルビ', 'HD', '使用')
            self.store.record(run['id'], [{'name': name, 'kind': 'material'}])
        self.store.new_run('アルビ', 'HD', '使用')
        path = self.store.folder/'output.csv'
        export_statistics(self.store, path)
        self.assertTrue(path.read_bytes().startswith(b'\xef\xbb\xbf'))
        with path.open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row['プレイヤー名'], 'A,"名前"')
            self.assertEqual(row['集計済み周回'], '2')
            self.assertEqual(row['未確認周回'], '1')
            self.assertEqual(row['出現率'], '0.5')

    def test_empty_material_statistics_keep_run_count(self):
        self.store.set_player_name('名前')
        run = self.store.new_run('アルビ', 'HD', '使用')
        self.store.record(run['id'], [{'name': '金貨', 'kind': 'excluded'}])
        path = self.store.folder/'output.csv'
        export_statistics(self.store, path)
        with path.open(encoding='utf-8-sig', newline='') as f:
            row = next(csv.DictReader(f))
        self.assertEqual(row['集計済み周回'], '1')
        self.assertEqual(row['アイテム'], '')

    def test_name_failure_rolls_back_and_anonymous_export_is_rejected(self):
        self.store.set_player_name('旧名')
        self.store.save = Mock(side_effect=OSError('disk error'))
        with self.assertRaises(OSError):
            self.store.set_player_name('新名')
        self.assertEqual(self.store.player_name, '旧名')
        unnamed = Store(self.store.folder/'other')
        with self.assertRaises(ValueError):
            export_statistics(unnamed, unnamed.folder/'output.csv')

    def test_preview_smooths_edges_without_changing_original(self):
        image = Image.new('RGB', (2, 2), 'black')
        image.putpixel((0, 0), (255, 255, 255))
        preview = pixel_preview(image)
        self.assertEqual(preview.size, (8, 8))
        self.assertTrue(any(0 < pixel[0] < 255 for pixel in preview.getdata()))
        self.assertEqual(set(image.getdata()), {(0, 0, 0), (255, 255, 255)})
        self.assertEqual(image.size, (2, 2))


if __name__ == '__main__':
    unittest.main()
