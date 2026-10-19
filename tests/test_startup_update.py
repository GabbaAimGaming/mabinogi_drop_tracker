import queue
import threading
import unittest
from unittest.mock import Mock, patch

from drop_tool import updater
from drop_tool.update_view import UpdateView


class StartupUpdateTests(unittest.TestCase):
    def view(self):
        view = UpdateView.__new__(UpdateView)
        view.app = Mock()
        view.app.busy = view.app.watching = False
        view.app.samples.lock.locked.return_value = False
        view.checking = view.installing = False
        view.startup = True
        view.startup_checked = False
        view.dialog = None
        view.work = Mock()
        view.button = Mock()
        view.url = Mock()
        view.url.get.return_value = updater.DEFAULT_SOURCE
        view.status = Mock()
        view.jobs = queue.Queue()
        return view

    def test_startup_checks_only_once(self):
        view = self.view()
        view.check = Mock()
        view.startup_check()
        view.startup_check()
        view.check.assert_called_once_with(startup=True)

    def test_slow_check_runs_in_background_without_saving_settings(self):
        view = self.view()
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        def slow_check(url, work):
            entered.set()
            try:
                release.wait(3)
                return {'version': updater.VERSION}
            finally:
                finished.set()
        with patch.object(updater, 'new_work', return_value=view.work), \
                patch.object(updater, 'check', side_effect=slow_check):
            try:
                view.check(startup=True)
                self.assertTrue(entered.wait(1))
                self.assertFalse(finished.is_set())
                view.app.save_setting.assert_not_called()
            finally:
                release.set()
                self.assertTrue(finished.wait(2))

    def test_latest_and_offline_startup_do_not_show_dialogs(self):
        view = self.view()
        with patch.object(updater, 'cleanup'), \
                patch('drop_tool.update_view.messagebox') as dialogs:
            view.offer({'version': updater.VERSION})
            view.failed('offline')
            self.assertEqual(dialogs.mock_calls, [])
        view.app.stop.assert_not_called()

    def test_decline_does_not_download_save_or_stop(self):
        view = self.view()
        with patch.object(updater, 'cleanup') as cleanup, \
                patch.object(updater, 'prepare') as prepare, \
                patch('drop_tool.update_view.messagebox.askyesno', return_value=False) as consent:
            view.offer({'version':'99.0', 'release_notes':'changes'})
            consent.assert_called_once()
            cleanup.assert_called_once()
            prepare.assert_not_called()
        view.app.store.save.assert_not_called()
        view.app.stop.assert_not_called()

    def test_offer_waits_for_monitoring_reading_and_saving(self):
        for state in ('watching', 'busy', 'saving'):
            with self.subTest(state=state):
                view = self.view()
                if state == 'saving':
                    view.app.samples.lock.locked.return_value = True
                else:
                    setattr(view.app, state, True)
                with patch('drop_tool.update_view.messagebox.askyesno') as consent:
                    view.offer({'version':'99.0'})
                    consent.assert_not_called()
                    delay, callback = view.app.root.after.call_args.args
                    self.assertEqual(delay, 1000)
                    view.app.watching = view.app.busy = False
                    view.app.samples.lock.locked.return_value = False
                    consent.return_value = False
                    with patch.object(updater, 'cleanup'):
                        callback()
                    consent.assert_called_once()

    def test_errors_after_yes_are_visible_and_never_install_unsaved_data(self):
        view = self.view()
        view.app.store.save.side_effect = OSError('cannot save')
        with patch.object(updater.sys, 'frozen', True, create=True), \
                patch.object(updater, 'cleanup'), \
                patch.object(updater, 'prepare') as prepare, \
                patch('drop_tool.update_view.messagebox.askyesno', return_value=True), \
                patch('drop_tool.update_view.messagebox.showerror') as error:
            view.offer({'version':'99.0'})
            error.assert_called_once()
            prepare.assert_not_called()
        view.app.stop.assert_not_called()

    def test_manual_check_still_reports_latest(self):
        view = self.view()
        view.startup = False
        with patch.object(updater, 'cleanup'), \
                patch('drop_tool.update_view.messagebox.showinfo') as info:
            view.offer({'version':updater.VERSION})
            info.assert_called_once()

    def test_yes_saves_and_stages_update_before_any_launch(self):
        view = self.view()
        info = {'version':'99.0', 'package':{'size':1024}}
        with patch.object(updater.sys, 'frozen', True, create=True), \
                patch('drop_tool.update_view.messagebox.askyesno', return_value=True), \
                patch('drop_tool.update_view.tk.Toplevel'), \
                patch('drop_tool.update_view.ttk.Label'), \
                patch('drop_tool.update_view.threading.Thread') as worker, \
                patch('drop_tool.update_view.shutil.disk_usage') as disk, \
                patch.object(updater, 'prepare', return_value='staged') as prepare, \
                patch.object(updater, 'launch') as launch:
            disk.return_value.free = 2**40
            view.offer(info)
            view.app.store.save.assert_called_once()
            view.app.stop.assert_called_once()
            self.assertTrue(view.installing)
            worker.return_value.start.assert_called_once()
            worker.call_args.kwargs['target']()
            prepare.assert_called_once()
            self.assertEqual(view.jobs.get_nowait(), ('prepared','staged'))
            launch.assert_not_called()
