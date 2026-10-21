"""証拠画像の世代管理と設定タブ。テキスト化・バックアップ済みの画像だけを削除する。"""
import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from drop_tool import retention, settings
from drop_tool.tracker import Store


def add_run(store, names=('素材A', '素材B'), confirm=True, status=None):
    run = store.new_run('アルビ', 'HD', '使用')
    labels = [{'name': n, 'raw': n, 'kind': 'material', 'image': Image.new('RGB', (40, 12))} for n in names]
    rows = store.persist_rows(run['id'], labels)
    store.record(run['id'], rows, require_review=True)
    if confirm:
        store.confirm(run['id'])
    if status:
        run['status'] = status
        store.save()
    return run


def images(store, run):
    return [store.folder / row['image'] for row in run['rows']]


class PruneEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)

    def test_keeps_newest_generations_and_deletes_older(self):
        runs = [add_run(self.store) for _ in range(5)]
        removed = retention.prune_evidence(self.store, 3)
        self.assertEqual(removed, 4)
        for run in runs[:2]:
            self.assertFalse(any(p.exists() for p in images(self.store, run)))
            self.assertFalse((self.store.folder / 'evidence' / run['id']).exists())
            self.assertIn('evidence_pruned', run)
        for run in runs[2:]:
            self.assertTrue(all(p.exists() for p in images(self.store, run)))
            self.assertNotIn('evidence_pruned', run)
        # テキストと統計は残る。
        reloaded = Store(self.store.folder)
        self.assertEqual(reloaded.stats(('アルビ', 'HD', '使用'))[0], 5)
        self.assertEqual([r['name'] for r in reloaded.find(runs[0]['id'])['rows']], ['素材A', '素材B'])
        self.assertIn('evidence_pruned', reloaded.find(runs[0]['id']))

    def test_unconfirmed_and_discarded_runs_are_never_deleted(self):
        review = add_run(self.store, confirm=False)
        discarded = add_run(self.store, status='discarded')
        for _ in range(3):
            add_run(self.store)
        retention.prune_evidence(self.store, 1)
        for run in (review, discarded):
            self.assertTrue(all(p.exists() for p in images(self.store, run)))

    def test_confirmed_run_with_unreviewed_row_is_kept(self):
        run = add_run(self.store)
        run['rows'][0]['kind'] = 'review'
        self.store.save()
        add_run(self.store)
        retention.prune_evidence(self.store, 1)
        self.assertTrue(all(p.exists() for p in images(self.store, run)))

    def test_text_not_yet_in_backup_is_kept(self):
        old = add_run(self.store)
        add_run(self.store)
        # 画面上だけで変更され、バックアップにまだ無い品名。
        old['rows'][0]['name'] = '未保存の修正'
        retention.prune_evidence(self.store, 1)
        self.assertTrue(all(p.exists() for p in images(self.store, old)))
        # 次回は保存とバックアップが揃うので削除される。
        retention.prune_evidence(self.store, 1)
        self.assertFalse(any(p.exists() for p in images(self.store, old)))

    def test_learned_templates_and_screenshot_are_untouched(self):
        (self.store.folder / 'labels').mkdir()
        learned = self.store.folder / 'labels' / 'x.png'
        Image.new('RGB', (10, 10)).save(learned)
        shot = self.store.folder / 'last-loot-capture.png'
        Image.new('RGB', (10, 10)).save(shot)
        for _ in range(4):
            add_run(self.store)
        retention.prune_evidence(self.store, 1)
        self.assertTrue(learned.exists())
        self.assertTrue(shot.exists())

    def test_locked_file_is_retried_later(self):
        old = add_run(self.store)
        add_run(self.store)
        locked = images(self.store, old)[0]
        original = Path.unlink

        def unlink(path, *args, **kwargs):
            if path == locked:
                raise PermissionError('in use')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'unlink', unlink):
            retention.prune_evidence(self.store, 1)
        self.assertTrue(locked.exists())
        self.assertNotIn('evidence_pruned', old)
        self.assertEqual(retention.prune_evidence(self.store, 1), 1)
        self.assertIn('evidence_pruned', old)

    def test_nothing_to_do_does_not_save(self):
        add_run(self.store)
        with patch.object(self.store, 'save') as save:
            self.assertEqual(retention.prune_evidence(self.store, 3), 0)
        save.assert_not_called()


class SettingsTests(unittest.TestCase):
    def test_defaults_and_validation(self):
        # [削減候補 2026-10-21] retention.load_settings/save_settingsのコメントアウトに合わせ、
        # 本体が使うsettings.load/saveで同じ内容を確認する。旧版は下にコメントで残す。確認後に旧版を削除
        def evidence(folder):
            loaded = settings.load(folder)
            return {key: loaded[key] for key in ('evidence_auto_delete', 'evidence_keep_runs')}
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(evidence(folder), {'evidence_auto_delete': True, 'evidence_keep_runs': 3})
            (Path(folder) / 'settings.json').write_text('{"evidence_keep_runs": -4, "evidence_auto_delete": "x"}', 'utf-8')
            self.assertEqual(evidence(folder)['evidence_keep_runs'], 3)
            (Path(folder) / 'settings.json').write_text('壊れた', 'utf-8')
            self.assertTrue(evidence(folder)['evidence_auto_delete'])
            settings.save(folder, evidence_auto_delete=False, evidence_keep_runs=10)
            self.assertEqual(evidence(folder), {'evidence_auto_delete': False, 'evidence_keep_runs': 10})
            with self.assertRaises(ValueError):
                settings.save(folder, evidence_auto_delete=True, evidence_keep_runs=0)
            self.assertEqual(json.loads((Path(folder) / 'settings.json').read_text('utf-8'))['evidence_keep_runs'], 10)
        # with tempfile.TemporaryDirectory() as folder:
        #     self.assertEqual(retention.load_settings(folder),
        #                      {'evidence_auto_delete': True, 'evidence_keep_runs': 3})
        #     (Path(folder) / 'settings.json').write_text('{"evidence_keep_runs": -4, "evidence_auto_delete": "x"}', 'utf-8')
        #     self.assertEqual(retention.load_settings(folder)['evidence_keep_runs'], 3)
        #     (Path(folder) / 'settings.json').write_text('壊れた', 'utf-8')
        #     self.assertTrue(retention.load_settings(folder)['evidence_auto_delete'])
        #     saved = retention.save_settings(folder, evidence_auto_delete=False, evidence_keep_runs=10)
        #     self.assertEqual(saved, {'evidence_auto_delete': False, 'evidence_keep_runs': 10})
        #     with self.assertRaises(ValueError):
        #         retention.save_settings(folder, evidence_auto_delete=True, evidence_keep_runs=0)
        #     self.assertEqual(json.loads((Path(folder) / 'settings.json').read_text('utf-8'))['evidence_keep_runs'], 10)


class SettingsTabTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(self.close)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        from drop_tool.app import App
        self.store = Store(self.temp.name)
        self.runs = [add_run(self.store) for _ in range(4)]
        self.app = App(self.root, self.store)
        self.root.update()

    def close(self):
        for job in self.root.tk.call('after', 'info'):
            self.root.after_cancel(job)
        self.root.destroy()

    def test_tab_is_appended_and_saves_generation_count(self):
        tabs = [self.app.notebook.tab(t, 'text') for t in self.app.notebook.tabs()]
        self.assertEqual(tabs[-1], '設定')
        self.assertEqual(tabs[:2], ['ドロップ統計', '周回履歴・確認待ち'])
        view = self.app.settings_views
        self.assertEqual(view.keep.get(), '3')
        view.keep.set('1')
        self.assertTrue(view.save())
        # [削減候補 2026-10-21] retention.load_settingsのコメントアウトに合わせsettings.loadへ。確認後に旧行を削除
        # self.assertEqual(retention.load_settings(self.store.folder)['evidence_keep_runs'], 1)
        self.assertEqual(settings.load(self.store.folder)['evidence_keep_runs'], 1)
        self.assertFalse(any(p.exists() for p in images(self.store, self.runs[0])))
        self.assertTrue(all(p.exists() for p in images(self.store, self.runs[-1])))
        self.assertIn('2枚', view.usage.get())

    def test_invalid_count_is_rejected(self):
        view = self.app.settings_views
        view.keep.set('0')
        with patch('drop_tool.settings_views.messagebox.showerror') as error:
            self.assertFalse(view.save())
        error.assert_called_once()
        self.assertTrue(all(p.exists() for p in images(self.store, self.runs[0])))

    def test_disabled_auto_delete_keeps_images(self):
        view = self.app.settings_views
        view.auto_delete.set(False)
        view.keep.set('1')
        view.save()
        self.assertTrue(all(p.exists() for p in images(self.store, self.runs[0])))

    def test_pruned_row_preview_and_learning_are_safe(self):
        retention.prune_evidence(self.store, 1)
        self.app.runs.selection_set(self.runs[0]['id'])
        self.app.select_run()
        self.app.rows.selection_set('0')
        self.app.select_row()
        self.assertIn('削除済み', self.app.status.get())
        with patch('drop_tool.app.messagebox.showerror') as error:
            self.app.correct_row('material')
        # 画像が無くても正式名への対応付けは可能。ただし候補の明示選択が必要。
        self.assertIn('辞書候補', error.call_args.args[1])


if __name__ == '__main__':
    unittest.main()
