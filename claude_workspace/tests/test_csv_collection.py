"""累積CSVの置換、条件別の分母、既存形式からの読込を検証する。"""
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from drop_tool.csv_collection import CsvCollection, read_csv, load_batch
from drop_tool.exporting import CSV_COLUMNS


class CsvCollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.store = CsvCollection(self.folder)

    def file(self, name, rows):
        path = self.folder / name
        with path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(CSV_COLUMNS)
            writer.writerows(rows)
        return path

    def row(self, player='A', count=2, item='素材', hits=1, dungeon='アルビ', near='使用'):
        return [player, dungeon, 'HD', near, count, 1, item, hits, '0.999']

    def test_weighted_total_not_average_of_rates(self):
        path = self.file('a.csv', [self.row('A', 2), self.row('B', 10)])
        self.store.replace(read_csv(path))
        result = self.store.aggregate()[('アルビ', 'HD', '使用')]
        self.assertEqual((result['count'], result['items']['素材']), (12, 2))
        self.assertAlmostEqual(result['items']['素材']/result['count'], 1/6)
        self.assertEqual(self.store.aggregate('A')[('アルビ','HD','使用')]['count'], 2)

    def test_denominator_counted_once_per_player_not_per_item(self):
        path = self.file('a.csv', [self.row(item='素材1'), self.row(item='素材2')])
        self.store.replace(read_csv(path))
        self.assertEqual(self.store.aggregate()[('アルビ','HD','使用')]['count'], 2)

    def test_no_material_snapshot_still_contributes_denominator(self):
        empty = self.row('B', 8, '', '')
        path = self.file('a.csv', [self.row(), empty])
        self.store.replace(read_csv(path))
        total = self.store.aggregate()[('アルビ','HD','使用')]
        self.assertEqual((total['count'], total['items']['素材']), (10, 1))

    def test_import_twice_and_replace_do_not_add_and_remove_stale_items(self):
        path = self.file('a.csv', [self.row(item='古い素材')])
        first = read_csv(path)
        self.store.replace(first)
        self.store.replace(first)
        self.store.replace(read_csv(self.file('b.csv', [self.row(count=4, item='新しい素材', hits=3)])))
        total = self.store.aggregate()[('アルビ','HD','使用')]
        self.assertEqual(total['count'], 4)
        self.assertEqual(total['items'], {'新しい素材': 3})

    def test_conditions_are_not_mixed(self):
        path = self.file('a.csv', [self.row(), self.row(near='不使用'), self.row(dungeon='ルンダ')])
        self.store.replace(read_csv(path))
        self.assertEqual(len(self.store.aggregate()), 3)

    def test_conflicting_batch_is_rejected(self):
        a = self.file('a.csv', [self.row(count=2)])
        b = self.file('b.csv', [self.row(count=8)])
        with self.assertRaisesRegex(ValueError, '異なるCSV'):
            load_batch([a,b])
        self.assertEqual(load_batch([a,a]), read_csv(a))
        self.assertEqual(self.store.groups, [])

    def test_invalid_counts_and_duplicate_items_are_rejected(self):
        for rows in ([self.row(hits=3)], [self.row(count=-1)],
                     [self.row(), self.row()], [self.row(), self.row(count=5,item='別の品')]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                read_csv(self.file('bad.csv', rows))

    def test_old_header_without_player_is_rejected(self):
        path = self.folder/'old.csv'
        path.write_text('ダンジョン,アイテム\nアルビ,素材', 'utf-8')
        with self.assertRaisesRegex(ValueError, 'プレイヤー名'):
            read_csv(path)

    def test_zero_count_does_not_divide_by_zero(self):
        self.store.replace(read_csv(self.file('a.csv', [self.row(count=0,item='',hits='')])))
        self.assertEqual(self.store.aggregate()[('アルビ','HD','使用')]['count'], 0)

    def test_restart_and_remove_player_preserve_other_person(self):
        self.store.replace(read_csv(self.file('a.csv', [self.row('カレン'), self.row('翠風')])))
        loaded = CsvCollection(self.folder)
        loaded.remove_player('カレン')
        self.assertEqual([g['player'] for g in CsvCollection(self.folder).groups], ['翠風'])
        self.assertTrue(list((self.folder/'backups').glob('csv-*.json')))

    def test_failed_write_preserves_previous_state(self):
        self.store.replace(read_csv(self.file('a.csv', [self.row()])))
        before = self.store.path.read_bytes()
        with patch.object(Path, 'replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.store.remove_player('A')
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(len(self.store.groups), 1)
