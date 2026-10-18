"""複数エリアの分母・対象条件を確認する回帰テスト。"""
import unittest
from drop_tool.csv_collection import filter_groups

class FilterTests(unittest.TestCase):
    def setUp(self):
        self.groups = {
            ('アルビ','HD','使用'):dict(count=10,pending=2,items={'素材':2}),
            ('アルビ','上級','未使用'):dict(count=5,pending=0,items={}),
            ('夢幻ラビ','誘惑','未使用'):dict(count=20,pending=3,items={'素材':8}),
            ('夢幻ラビ','通常','未使用'):dict(count=100,pending=0,items={'素材':90})}
    def test_combined_excludes_other_difficulty_and_preserves_empty_runs(self):
        result = next(iter(filter_groups(self.groups,'combined').values()))
        self.assertEqual(result,dict(count=35,pending=5,items={'素材':10}))
        self.assertEqual(len(self.groups),4)
    def test_dungeon_and_exact_condition(self):
        result = next(iter(filter_groups(self.groups,'dungeon','アルビ').values()))
        self.assertEqual(result['count'],15)
        context = ('アルビ','HD','使用')
        self.assertEqual(filter_groups(self.groups,'context',context),{context:self.groups[context]})
    def test_empty_is_not_zero_rate_record(self):
        self.assertEqual(filter_groups({},'combined'),{})
        self.assertEqual(filter_groups(self.groups,'dungeon','キア'),{})
