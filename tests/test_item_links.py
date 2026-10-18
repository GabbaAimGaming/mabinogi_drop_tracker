"""対応付けの可逆性・原記録保持・同一周回の重複排除・登録の取消を検証。"""
import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from drop_tool.tracker import Store
from drop_tool.item_catalog import ItemCatalog
from drop_tool.item_links import row_identity,resolve_name
from drop_tool.item_registration import assign,unlink
from drop_tool.exporting import export_statistics

TARGET='壊れた輪状構造体'
TYPO='壊れた穀状構造体'
CONTEXT=('アルビ','HD','使用')


class ItemLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name);self.catalog=ItemCatalog(self.store)

    def run_with(self,*names,kind='material'):
        run=self.store.new_run(*CONTEXT)
        self.store.record(run['id'],[{'name':n,'kind':kind,'image':''} for n in names])
        return run

    def test_alias_union_keeps_original_rows_and_denominator(self):
        self.run_with(TYPO,TARGET);self.run_with(TYPO);self.run_with(TARGET)
        excluded=self.run_with(TYPO);excluded['status']='discarded'
        self.run_with(TYPO,kind='review')
        original=copy.deepcopy(self.store.data['runs'])
        assign(self.catalog,TYPO,TARGET,'material')
        self.assertEqual(self.store.data['runs'],original)
        n,pending,rows=self.store.stats(CONTEXT)
        self.assertEqual((n,pending),(3,1))
        self.assertEqual(rows,[(TARGET,3,1.0)])
        restored=Store(self.temp.name)
        self.assertEqual(restored.stats(CONTEXT),(n,pending,rows))

    def test_unlink_restores_separate_counts(self):
        self.run_with(TYPO,TARGET);self.run_with(TYPO)
        original=self.store.stats(CONTEXT)
        assign(self.catalog,TYPO,TARGET,'material')
        unlink(self.catalog,[TYPO])
        self.assertEqual(self.store.stats(CONTEXT),original)
        self.assertIsNotNone(self.catalog.find(TYPO))

    def test_change_destination_and_prevent_cycle(self):
        self.run_with(TYPO)
        assign(self.catalog,TYPO,TARGET,'material')
        assign(self.catalog,TYPO,'魔力の黄金の糸','material')
        self.assertEqual(self.store.stats(CONTEXT)[2][0][0],'魔力の黄金の糸')
        with self.assertRaises(ValueError):assign(self.catalog,'魔力の黄金の糸',TYPO,'material')

    def test_corrupt_cycle_is_rejected_on_load(self):
        self.store.data['item_links']={'a':'b','b':'a'};self.store.save()
        with self.assertRaises(ValueError):Store(self.temp.name)

    def test_target_policy_confirmed_and_names_unchanged(self):
        run=self.run_with(TYPO,kind='review')
        assign(self.catalog,TYPO,TARGET,'material',run_id=run['id'],row_index=0)
        self.assertEqual(run['rows'][0]['name'],TYPO)
        self.assertEqual(run['rows'][0]['kind'],'review')
        self.assertEqual(self.catalog.classify(TARGET),'material')
        self.assertEqual(run['status'],'review')
        self.store.confirm(run['id'])
        self.assertEqual(self.store.stats(CONTEXT)[2],[(TARGET,1,1.0)])

    def test_pending_registration_does_not_confirm_item(self):
        run=self.run_with(TYPO,kind='review')
        assign(self.catalog,TYPO,TARGET,'review',run_id=run['id'],row_index=0)
        self.assertEqual(self.catalog.classify(TARGET),'review')
        with self.assertRaises(ValueError):self.store.confirm(run['id'])

    def test_unknown_placeholder_is_only_resolved_for_selected_row(self):
        run=self.run_with('読取不明','読取不明',kind='review')
        assign(self.catalog,'読取不明',TARGET,'material',run_id=run['id'],row_index=0)
        self.assertNotIn('読取不明',self.store.data.get('item_links',{}))
        self.assertEqual(row_identity(self.store.data,run['rows'][0]),(TARGET,'material'))
        self.assertEqual(row_identity(self.store.data,run['rows'][1]),('読取不明','review'))

    def test_new_item_and_duplicates_and_search(self):
        assign(self.catalog,'','新素材ABC','review',new=True)
        self.assertIn('新素材ABC',self.catalog.search('素材A'))
        self.assertIn(TARGET,self.catalog.search('壊れた穀状構造体'))
        self.assertIn(TARGET,self.catalog.search(''))
        with self.assertRaises(ValueError):assign(self.catalog,'','新素材ABC','material',new=True)
        with self.assertRaises(ValueError):assign(self.catalog,'','未登録名','material')

    def test_removed_image_does_not_prevent_name_assignment(self):
        run=self.run_with(TYPO,kind='review')
        run['evidence_pruned']='old'
        assign(self.catalog,TYPO,TARGET,'excluded',run_id=run['id'],row_index=0)
        self.assertEqual(row_identity(self.store.data,run['rows'][0]),(TARGET,'excluded'))
        self.assertEqual(self.store.data['templates'],[])

    def test_old_template_is_preserved_and_same_new_template_not_duplicated(self):
        old={'name':TYPO,'kind':'review','path':'labels/old.png'}
        self.store.data['templates'].append(old.copy())
        image=Image.new('RGB',(40,14),'white')
        for _ in range(2):assign(self.catalog,TYPO,TARGET,'material',image=image)
        self.assertIn(old,self.store.data['templates'])
        self.assertEqual(len(self.store.data['templates']),2)

    def test_failed_save_rolls_back_names_policy_link_and_row(self):
        run=self.run_with(TYPO,kind='review');before=copy.deepcopy(self.store.data)
        with patch.object(self.store,'save',side_effect=OSError('full')):
            with self.assertRaises(OSError):assign(self.catalog,TYPO,TARGET,'material',run_id=run['id'],row_index=0)
        self.assertEqual(self.store.data,before)

    def test_csv_uses_resolved_union(self):
        self.run_with(TYPO,TARGET);self.run_with(TYPO)
        self.store.set_player_name('確認用')
        assign(self.catalog,TYPO,TARGET,'material')
        path=Path(self.temp.name)/'stats.csv';export_statistics(self.store,path)
        with path.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['アイテム'],TARGET)
        self.assertEqual(rows[0]['出現周回'],'2')


class RegistrationUITests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from drop_tool.app import App
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=tk.Tk();self.root.withdraw()
        self.app=App(self.root,Store(self.temp.name))
        self.root.update_idletasks()
        self.addCleanup(self.close)
        run=self.app.store.new_run(*CONTEXT)
        self.app.store.record(run['id'],[{'name':TYPO,'kind':'review','image':''}],require_review=True)
        self.run=run;self.app.refresh();self.app.runs.selection_set(run['id'])
        self.app.select_run();self.app.rows.selection_set('0');self.app.select_row()

    def close(self):
        for job in self.root.tk.call('after','info'):self.root.after_cancel(job)
        self.root.destroy()

    def test_search_invalidates_old_selection_without_writing(self):
        original=copy.deepcopy(self.app.store.data)
        self.app.candidates.set(TARGET)
        self.app.correct.set('黄金')
        self.assertEqual(self.app.candidates.get(),'')
        self.assertIn('魔力の黄金の糸',self.app.candidates.cget('values'))
        self.assertEqual(self.app.store.data,original)

    def test_cancel_writes_nothing(self):
        original=copy.deepcopy(self.app.store.data)
        self.app.candidates.set(TARGET)
        with patch('drop_tool.app.messagebox.askyesno',return_value=False) as ask:
            self.app.correct_row('material')
        ask.assert_called_once()
        self.assertEqual(self.app.store.data,original)

    def test_confirm_updates_dictionary_and_keeps_original(self):
        self.app.candidates.set(TARGET)
        with patch('drop_tool.app.messagebox.askyesno',return_value=True):self.app.correct_row('material')
        self.assertEqual(self.run['rows'][0]['name'],TYPO)
        self.assertEqual(self.app.vision.catalog.classify(TARGET),'material')
        self.assertEqual(self.run['status'],'review')

    def test_new_name_requires_explicit_button_and_confirmation(self):
        self.app.correct.set('新素材XYZ')
        with patch('drop_tool.app.messagebox.showerror') as error:self.app.correct_row('material')
        error.assert_called_once()
        with patch('drop_tool.app.messagebox.askyesno',return_value=True):self.app.correct_row('material',new=True)
        self.assertIsNotNone(self.app.vision.catalog.find('新素材XYZ'))

    def test_item_management_cancel_and_unlink(self):
        view=self.app.item_views
        assign(self.app.vision.catalog,TYPO,TARGET,'material')
        view.after_registration();view.search.set(TYPO);view.table.selection_set(TYPO)
        with patch('drop_tool.item_views.messagebox.askyesno',return_value=False):view.unlink_selected()
        self.assertEqual(resolve_name(self.app.store.data,TYPO),TARGET)
        with patch('drop_tool.item_views.messagebox.askyesno',return_value=True):view.unlink_selected()
        self.assertEqual(resolve_name(self.app.store.data,TYPO),TYPO)
