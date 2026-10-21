import unittest,tempfile
from drop_tool.tracker import Store
from drop_tool.item_catalog import ItemCatalog

class NonChestLootTests(unittest.TestCase):
    def test_fynni_is_excluded_but_explicit_user_policy_wins(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);catalog=ItemCatalog(store)
            for name in ['フィニージェム:ゴースト','フィニージェム:サキュバス','フィニージエム:サキュバス']:
                self.assertEqual(catalog.classify(name),'excluded')
            catalog.set_policy(['フィニージェム:ゴースト'],'material')
            self.assertEqual(catalog.classify('フィニージェム:ゴースト'),'material')
            # 別品とつながった行まで非宝箱品として捨てない。
            self.assertEqual(catalog.classify('6段階赤い改造石フィニージェム:ゴースト'),'review')
