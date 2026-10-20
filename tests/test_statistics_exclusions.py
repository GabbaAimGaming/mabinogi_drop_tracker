"""現在の除外を過去の集計へ反映し、観測・分母・未確認状態は保持する。"""
import copy
import csv
import tempfile
import unittest
from pathlib import Path

from drop_tool.exporting import export_statistics
from drop_tool.item_catalog import ItemCatalog
from drop_tool.item_registration import assign
from drop_tool.tracker import Store


CONTEXT = ('アルビ', 'HD', '使用')
GEM = 'スピリットジェム'
MATERIAL = '魔力の黄金の糸'


class StatisticsExclusionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.catalog = ItemCatalog(self.store)

    def record(self, name, kind='material', **fields):
        run = self.store.new_run(*CONTEXT)
        self.store.record(run['id'], [{'name': name, 'kind': kind, **fields}])
        return run

    def test_default_exclusion_removes_old_count_without_rewriting_history(self):
        self.record(GEM)
        self.record(GEM + '（５００）', reviewed_kind='material')
        self.record(MATERIAL)
        before = copy.deepcopy(self.store.data)
        self.assertEqual(self.store.stats(CONTEXT), (3, 0, [(MATERIAL, 1, 1 / 3)]))
        self.assertEqual(self.store.data, before)

    def test_policy_change_is_immediate_reversible_and_survives_reload(self):
        self.record(MATERIAL)
        self.catalog.set_policy([MATERIAL], 'excluded')
        self.assertEqual(self.store.stats(CONTEXT), (1, 0, []))
        self.assertEqual(Store(self.temp.name).stats(CONTEXT), (1, 0, []))
        self.catalog.set_policy([MATERIAL], 'material')
        self.assertEqual(self.store.stats(CONTEXT), (1, 0, [(MATERIAL, 1, 1.)]))

    def test_explicit_include_overrides_default_exclusion_for_quantity(self):
        self.record(GEM + '(500)')
        self.catalog.set_policy([GEM], 'material')
        self.assertEqual(self.store.stats(CONTEXT)[2], [(GEM + '(500)', 1, 1.)])

    def test_exclusion_uses_resolved_name_and_keeps_other_item_and_pending(self):
        run = self.record('誤読ジェム', resolved_name=GEM, reviewed_kind='material')
        run['rows'].append({'name': MATERIAL, 'kind': 'material'})
        self.record('未確認素材', 'review')
        self.store.new_run(*CONTEXT)
        self.assertEqual(self.store.stats(CONTEXT), (1, 2, [(MATERIAL, 1, 1.)]))

    def test_exclusion_applies_after_name_link_resolution(self):
        self.record('スビリットジェム')
        assign(self.catalog, 'スビリットジェム', GEM, 'excluded')
        self.assertEqual(self.store.stats(CONTEXT), (1, 0, []))

    def test_include_does_not_promote_old_excluded_or_unreviewed_rows(self):
        run = self.record(MATERIAL, 'excluded')
        run['rows'].append({'name': MATERIAL, 'kind': 'review'})
        self.catalog.set_policy([MATERIAL], 'material')
        self.assertEqual(self.store.stats(CONTEXT), (1, 0, []))

    def test_csv_removes_excluded_item_and_keeps_denominator(self):
        self.record(GEM)
        self.record(MATERIAL)
        self.store.set_player_name('検証用')
        path = Path(self.temp.name) / 'stats.csv'
        export_statistics(self.store, path)
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual([r['アイテム'] for r in rows], [MATERIAL])
        self.assertEqual(rows[0]['集計済み周回'], '2')
        self.assertEqual(rows[0]['出現率'], '0.5')

    def test_excluded_only_export_still_has_context_and_denominator(self):
        self.record(GEM)
        self.store.set_player_name('検証用')
        path = Path(self.temp.name) / 'stats.csv'
        export_statistics(self.store, path)
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['アイテム'], '')
        self.assertEqual(rows[0]['集計済み周回'], '1')
