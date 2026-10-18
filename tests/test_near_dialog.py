import json
import tempfile
import unittest
import queue
from unittest.mock import Mock
from PIL import Image
from drop_tool.config import ROOT
from drop_tool.near_dialog import NearDialogDetector
from drop_tool.reward_gate import RewardGate
from drop_tool.item_catalog import ItemCatalog, lookup_key
from drop_tool.tracker import Store


class NearGateTests(unittest.TestCase):
    def test_dialog_resets_elapsed_and_never_triggers(self):
        gate = RewardGate()
        for t in (1, 2, 3):
            self.assertFalse(gate.observe(True, True, t))
        for t in range(4, 10):
            self.assertFalse(gate.observe(True, True, t, blocked=True))
            self.assertEqual(gate.elapsed(t), 0)
        for t in (10, 11, 12):
            self.assertFalse(gate.observe(False, True, t))
        self.assertTrue(gate.observe(False, True, 13))

    def test_cancel_does_not_trigger_and_hidden_chest_expires(self):
        gate = RewardGate()
        gate.observe(True, False, 1)
        for t in range(2, 20):
            self.assertFalse(gate.observe(False, True, t, blocked=True))
        for t in range(20, 26):
            self.assertFalse(gate.observe(False, True, t))
        gate.reset()
        gate.observe(True, False, 1, blocked=True)
        for t in range(2, 10):
            self.assertFalse(gate.observe(True, False, t))

    def test_fixed_features_both_required(self):
        detector = NearDialogDetector()
        im = Image.new('RGB', (800, 600), (35, 35, 35))
        with Image.open(ROOT/'assets/near-dialog/question.png') as q:
            im.paste(q, (184, 177))
        self.assertFalse(detector.detect(im))
        with Image.open(ROOT/'assets/near-dialog/buttons.png') as b:
            im.paste(b, (205, 255))
        self.assertTrue(detector.detect(im))

    def test_app_suppresses_dialog_even_when_chest_visible(self):
        from drop_tool.app import App
        im = Image.new('RGB', (800, 600), (35, 35, 35))
        for name, pos in (('question', (184,177)), ('buttons', (205,255))):
            with Image.open(ROOT/'assets/near-dialog'/f'{name}.png') as feature:
                im.paste(feature, pos)
        app = App.__new__(App)
        app.busy=False; app.epoch=0; app.hwnd=1; app.read_attempts=0
        app.settings={}; app.jobs=queue.Queue(); app.scan_trace=[]
        app.chest_detector=Mock(); app.chest_detector.detect.return_value={'found':True}
        app.reward_gate=RewardGate(seconds=0)
        app.vision=Mock(); app.grab=Mock(return_value=im)
        app.submit('live')
        event = app.jobs.get(timeout=10)
        self.assertEqual(event[1], 'scan')
        self.assertTrue(event[2]['near_dialog'])
        self.assertFalse(event[2]['alt'])
        self.assertIsNone(app.reward_gate.since)
        app.vision.analyze.assert_not_called()


class DictionaryUpdateTests(unittest.TestCase):
    def test_unique_names_and_source_ids(self):
        master = json.loads((ROOT/'item-master.json').read_text('utf-8'))
        self.assertGreaterEqual(len(master['items']), 440)
        self.assertEqual(len({lookup_key(x['name']) for x in master['items']}), len(master['items']))
        self.assertEqual(len({x['id'] for x in master['items']}), len(master['items']))
        for item in master['items']:
            self.assertTrue(set(item['source_ids']).issubset(master['sources']))

    def test_old_user_policy_and_history_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            store.data['overrides']['玲瓏たる羽根'] = 'excluded'
            run = store.new_run('夢幻ラビ', '誘惑', '使用')
            store.record(run['id'], [{'name':'旧誤登録', 'kind':'material'}])
            store.data.setdefault('item_links', {})['旧誤登録'] = '玲瓏たる羽根'
            store.save()
            before = json.dumps(store.data, ensure_ascii=False, sort_keys=True)
            catalog = ItemCatalog(store)
            self.assertEqual(catalog.classify('玲瓏たる羽根'), 'excluded')
            self.assertEqual(catalog.classify('旧誤登録'), 'excluded')
            self.assertEqual(catalog.classify('守護の黙示録'), 'review')
            self.assertEqual(before, json.dumps(store.data, ensure_ascii=False, sort_keys=True))
            self.assertIn('専用エンチャントスクロール・アエロ', catalog.search('アエロ'))
