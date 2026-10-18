import tempfile
import unittest
from drop_tool.tracker import Store
from drop_tool.item_catalog import ItemCatalog, lookup_key


class DictionarySupplementTests(unittest.TestCase):
    def test_card_variants_and_meteor_are_separate_names(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog=ItemCatalog(Store(folder))
            names=[]
            for kind in ('ALL','累積レベル','ペットポイント','召喚時間','カバン'):
                for grade in (('下級','中級','上級') if kind=='ALL' else ('下級','中級','上級','最上級')):
                    name=f'封印されたペット成長カード[{kind}-{grade}]'
                    self.assertEqual(catalog.find(name)['name'],name)
                    names.append(name)
            self.assertEqual(len({lookup_key(n) for n in names}),19)
            top='封印されたペット成長カード[ペットポイント-上級]'
            catalog.set_policy([top],'material')
            self.assertEqual(catalog.classify(top),'material')
            self.assertEqual(catalog.classify(top.replace('上級','中級')),'review')
            self.assertEqual(catalog.classify('封印されたペット成長カード'),'review')
            self.assertIsNotNone(catalog.find('専用エンチャントスクロール・メテオロイド'))
