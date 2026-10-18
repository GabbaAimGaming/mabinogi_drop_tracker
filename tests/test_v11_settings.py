import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from drop_tool import settings
from drop_tool.tracker import Store,SHADOW_MISSIONS
from drop_tool.item_catalog import ItemCatalog
from drop_tool.app import App

class UpdatedSettingsTests(unittest.TestCase):
    def test_old_share_setting_is_ignored_and_removed_on_save(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json'
            path.write_text(json.dumps({'window_share':True,'scan_mode':'center','future_option':42}))
            self.assertNotIn('window_share',settings.load(folder))
            result=settings.save(folder,evidence_keep_runs=4)
            self.assertEqual(result['scan_mode'],'center')
            saved=json.loads(path.read_text())
            self.assertNotIn('window_share',saved)
            self.assertEqual(saved['future_option'],42)

    def test_shadow_selection_sets_elite_and_no_near(self):
        for mission in SHADOW_MISSIONS:
            app=App.__new__(App)
            app.last_context=('アルビ','HD');app.dungeon=Mock();app.dungeon.get.return_value=mission
            app.difficulty=Mock();app.difficulty.get.return_value='エリート';app.near=Mock()
            app.context_changed()
            app.difficulty.set.assert_called_with('エリート')
            app.near.set.assert_called_with('不使用')

    def test_background_capture_is_not_ready(self):
        app=App.__new__(App)
        with patch('drop_tool.app.capture.active',return_value=False):
            self.assertFalse(app.ready(42))

    def test_orb_alias_and_shadow_types_do_not_auto_confirm(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog=ItemCatalog(Store(folder))
            alias='ベルシウスアークトゥルスオーブ'
            self.assertEqual(catalog.find(alias)['name'],'ペルシウスアークトゥルスオーブ')
            self.assertEqual(catalog.classify(alias),'review')
            self.assertIsNotNone(catalog.find('ペルシウスペレグリンサイズ'))
            self.assertIsNotNone(catalog.find('エンチャントスクロール・相性'))
            self.assertIsNone(catalog.find('専用エンチャントスクロール・相性'))
            for name in ['蒸留された','蒸発された','鋼鉄の','独白','傍白','レプリカ','カーテンコール']:
                self.assertIsNotNone(catalog.find('専用エンチャントスクロール・'+name))
