"""埋込み配置と小画面の操作性、EXE保存先の切替を確認する。"""
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from pathlib import Path
from unittest.mock import patch
from drop_tool.app import App
from drop_tool.tracker import Store
from drop_tool.config import application_root


class RootPathTests(unittest.TestCase):
    def test_frozen_root_follows_executable_not_build_machine(self):
        expected = Path(tempfile.gettempdir()).resolve()
        with patch.object(sys, 'frozen', True, create=True), \
                patch.object(sys, 'executable', str(expected / 'KarenDrop.exe')):
            self.assertEqual(application_root(), expected)


class KarenUITests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(self.close_window)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = App(self.root, Store(self.temp.name))
        self.root.geometry('1120x920')
        self.root.update()

    def close_window(self):
        # 複数Tkを順に作るテストで、前の画面の定期処理を次の画面へ残さない。
        for job in self.root.tk.call('after', 'info'):
            self.root.after_cancel(job)
        self.root.destroy()

    def test_character_is_embedded_without_overlay(self):
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        self.assertFalse(any(isinstance(w, tk.Toplevel) for w in descendants(self.root)))
        self.assertEqual(self.app.banner.photo.width(), 90)
        self.assertIs(self.app.banner.button.master, self.app.banner)

    def test_character_points_to_button_right_side(self):
        banner = self.app.banner
        image_x, image_y = banner.coords(banner.character)
        button_right, button_top = banner.coords(banner.button_item)
        self.assertGreater(image_x + 8, button_right)
        self.assertLess(image_x + 8 - button_right, 35)
        self.assertGreater(image_y + 36, button_top)

    def test_small_window_has_scrollable_content(self):
        self.root.geometry('780x600')
        self.root.update()
        page = self.app.page
        self.assertTrue(page.vertical.winfo_ismapped())
        self.assertTrue(page.horizontal.winfo_ismapped())
        self.assertLess(page.canvas.yview()[1], 1)
        page.canvas.yview_moveto(1)
        self.root.update()
        self.assertAlmostEqual(page.canvas.yview()[1], 1)

    def test_wide_window_does_not_need_scrollbars(self):
        self.assertFalse(self.app.page.vertical.winfo_ismapped())
        self.assertFalse(self.app.page.horizontal.winfo_ismapped())

    def test_history_and_items_share_draggable_space(self):
        self.app.notebook.select(1)
        self.root.update()
        split = self.app.review_split
        before = self.app.runs.winfo_height()
        x, y = split.sash_coord(0)
        split.sash_place(0, x, y + 70)
        self.root.update()
        self.assertGreater(self.app.runs.winfo_height(), before + 40)
        self.assertGreater(self.app.rows.winfo_height(), 40)

    def test_selected_tab_has_greater_vertical_padding(self):
        style = ttk.Style(self.root)
        selected = [int(str(v)) for v in self.root.tk.splitlist(style.lookup('TNotebook.Tab', 'padding', ('selected',)))]
        normal = [int(str(v)) for v in self.root.tk.splitlist(style.lookup('TNotebook.Tab', 'padding', ('!selected',)))]
        self.assertGreater(selected[1] + selected[3], normal[1] + normal[3])

    def test_csv_tabs_show_weighted_total_and_personal_filter(self):
        views = self.app.csv_views
        views.collection.replace([
            dict(player='A',dungeon='アルビ',difficulty='HD',near='使用',count=2,pending=0,items={'素材':1}),
            dict(player='B',dungeon='アルビ',difficulty='HD',near='使用',count=10,pending=0,items={'素材':1})])
        views.refresh()
        total = views.views[1]['table']
        values = total.item(total.get_children()[0], 'values')
        self.assertEqual(tuple(values[-3:]), ('2','12','16.67%'))
        personal = views.views[0]
        personal['player'].set('B')
        views.refresh()
        values = personal['table'].item(personal['table'].get_children()[0], 'values')
        self.assertEqual(tuple(values[-3:]), ('1','10','10.00%'))


    def test_item_management_bulk_filter_and_restart(self):
        view = self.app.item_views
        self.app.notebook.select(view.frame)
        view.search.set('魔力の黄金の糸')
        self.root.update()
        keys = view.table.get_children()
        self.assertEqual(len(keys), 1)
        view.table.selection_set(keys)
        view.set_selected('material')
        self.assertEqual(view.table.item(keys[0], 'values')[-1], '集計')
        from drop_tool.item_catalog import ItemCatalog
        self.assertEqual(ItemCatalog(Store(self.temp.name)).classify('魔力の黄金の糸'), 'material')
        view.kind.set('除外')
        view.refresh()
        self.assertEqual(view.table.get_children(), ())

    def test_unregistered_notice_is_grouped_and_not_saved_as_official(self):
        run = self.app.store.new_run('アルビ','HD','使用')
        self.app.active_id = run['id']
        self.app.refresh()
        result = {'labels': [{'name':'未知A','registered':False},
                             {'name':'未知B','registered':False},
                             {'name':'未知A','registered':False}]}
        with patch('drop_tool.app.messagebox.showinfo') as notice:
            self.app.notify_unregistered(result)
        self.assertEqual(notice.call_count, 1)
        self.assertIn('2種類', notice.call_args.args[1])
        self.assertIsNone(self.app.vision.catalog.find('未知A'))

    def test_preview_keeps_dictionary_controls_reachable(self):
        from PIL import Image
        self.root.geometry('1020x760')
        run = self.app.store.new_run('アルビ','HD','使用')
        rows = self.app.store.persist_rows(run['id'], [{'name':'誤読', 'kind':'review', 'image':Image.new('RGB',(200,20))}])
        self.app.store.record(run['id'], rows)
        self.app.refresh()
        self.app.notebook.select(1)
        self.app.runs.selection_set(run['id'])
        self.app.select_run()
        self.app.rows.selection_set('0')
        self.app.select_row()
        self.root.update()
        self.app.page.canvas.yview_moveto(1)
        self.root.update()
        self.assertTrue(self.app.candidates.winfo_ismapped())
        bottom = self.app.candidates.winfo_rooty() + self.app.candidates.winfo_height()
        self.assertLess(bottom, self.root.winfo_rooty() + self.root.winfo_height())
