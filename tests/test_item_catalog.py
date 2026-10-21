"""辞書導入で過去統計・旧学習・除外設定を壊さないことを検証する。"""
import copy
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from drop_tool.tracker import Store
from drop_tool.item_catalog import ItemCatalog, lookup_key
from drop_tool.vision import Vision
from drop_tool.item_registration import assign


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.catalog = ItemCatalog(self.store)

    def test_known_name_is_not_automatic_permission(self):
        self.assertIsNotNone(self.catalog.find('魔力の黄金の糸'))
        self.assertEqual(self.catalog.classify('魔力の黄金の糸'), 'review')
        self.assertEqual(self.catalog.classify('炎の糸'), 'excluded')
        self.assertEqual(self.catalog.classify('金貨'), 'excluded')
        self.assertEqual(self.catalog.classify('スピリットジェム(500)'), 'excluded')

    def test_quantity_normalization_preserves_gender_and_suffix(self):
        self.assertEqual(lookup_key('スピリットジェム（５００）'), 'スピリットジェム')
        self.assertNotEqual(lookup_key('靴(女性用)'), lookup_key('靴(男性用)'))
        self.assertIsNotNone(self.catalog.find('エンチャントスクロール・スケルトン'))
        self.assertIsNone(self.catalog.find('スケルトン'))

    def test_bulk_policy_persists_and_does_not_rewrite_history(self):
        run = self.store.new_run('アルビ', 'HD', '使用')
        self.store.record(run['id'], [{'name': '炎の糸', 'kind': 'excluded'}])
        history = copy.deepcopy(self.store.data['runs'])
        self.catalog.set_policy(['炎の糸', '魔力の黄金の糸'], 'material')
        new = ItemCatalog(Store(self.store.folder))
        self.assertEqual(new.classify('炎の糸'), 'material')
        self.assertEqual(new.classify('魔力の黄金の糸'), 'material')
        self.assertEqual(self.store.data['runs'], history)
        with self.assertRaises(ValueError):
            self.catalog.apply_pending(run['id'])

    def test_unknown_registration_can_remain_pending(self):
        self.catalog.set_policy(['新しい素材'], 'review')
        fresh = ItemCatalog(Store(self.store.folder))
        self.assertIsNotNone(fresh.find('新しい素材'))
        self.assertEqual(fresh.classify('新しい素材'), 'review')

    def test_old_learning_and_quantity_policy_migrate(self):
        self.store.data['overrides']['スピリットジェム(500)'] = 'material'
        self.catalog = ItemCatalog(self.store)
        self.assertEqual(self.catalog.classify('スピリットジェム(500)'), 'material')
        self.catalog.set_policy(['スピリットジェム'], 'review')
        self.assertEqual(self.catalog.classify('スピリットジェム(500)'), 'review')

    def test_failed_save_restores_settings(self):
        old = copy.deepcopy(self.store.data)
        with patch.object(self.store, 'save', side_effect=OSError('full')):
            with self.assertRaises(OSError):
                self.catalog.set_policy(['魔力の黄金の糸'], 'material')
        self.assertEqual(self.store.data, old)

    def test_explicit_apply_only_changes_pending_rows(self):
        run = self.store.new_run('アルビ', 'HD', '使用')
        self.store.record(run['id'], [{'name': '魔力の黄金の糸', 'kind': 'review'}])
        self.catalog.set_policy(['魔力の黄金の糸'], 'material')
        self.assertEqual(run['rows'][0]['kind'], 'review')
        self.catalog.apply_pending(run['id'])
        self.assertEqual(run['rows'][0]['kind'], 'material')
        self.assertEqual(run['status'], 'review')
        self.store.confirm(run['id'])
        self.assertEqual(self.store.stats(('アルビ','HD','使用'))[0], 1)

    def test_ocr_typo_proposes_but_never_replaces(self):
        vision = Vision(self.store)
        image = Image.new('RGB', (100, 14), 'white')
        with patch.object(vision, 'boxes', return_value=[image]), \
             patch.object(vision, 'recognize_template', return_value=None), \
             patch.object(vision, 'ocr_suggestions', return_value=['魔カの黄金の糸']):
            label = vision.analyze(image)['labels'][0]
        self.assertFalse(label['registered'])
        self.assertEqual(label['name'], '魔カの黄金の糸')
        self.assertEqual(label['kind'], 'review')
        self.assertIn('魔力の黄金の糸', label['candidates'])

    def test_ocr_exact_match_uses_saved_policy_but_requires_run_confirmation(self):
        self.catalog.set_policy(['魔力の黄金の糸'], 'material')
        vision = Vision(self.store)
        image = Image.new('RGB', (100, 14), 'white')
        with patch.object(vision, 'boxes', return_value=[image]), \
             patch.object(vision, 'recognize_template', return_value=None), \
             patch.object(vision, 'ocr_suggestions', return_value=['魔力の 黄金の糸']):
            label = vision.analyze(image)['labels'][0]
        self.assertTrue(label['registered'])
        self.assertEqual(label['name'], '魔力の黄金の糸')
        self.assertEqual(label['kind'], 'material')

    def test_image_learning_and_row_change_rollback_together(self):
        run = self.store.new_run('アルビ', 'HD', '使用')
        self.store.record(run['id'], [{'name': '誤読', 'kind': 'review'}])
        # [削減候補 2026-10-21] Vision.learnのコメントアウトに合わせ、本体の経路（item_registration.assign）で
        # 「画像の学習と行の変更が保存失敗時にまとめて戻る」ことを確認する。旧版は下にコメントで残す。確認後に旧版を削除
        old = copy.deepcopy(self.store.data)
        with patch.object(self.store, 'save', side_effect=OSError('full')):
            with self.assertRaises(OSError):
                assign(self.catalog, '誤読', '魔力の黄金の糸', 'review', image=Image.new('RGB',(20,10)),
                       run_id=run['id'], row_index=0)
        self.assertEqual(self.store.data, old)
        # vision = Vision(self.store)
        # old = copy.deepcopy(self.store.data)
        # with patch.object(self.store, 'save', side_effect=OSError('full')):
        #     with self.assertRaises(OSError):
        #         vision.learn('魔力の黄金の糸', 'review', Image.new('RGB',(20,10)),
        #                      run_id=run['id'], row_index=0)
        # self.assertEqual(self.store.data, old)
