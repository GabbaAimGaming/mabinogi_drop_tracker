import queue
import unittest
from unittest.mock import Mock, patch
from drop_tool.update_view import UpdateView
from drop_tool import updater


class OldReleaseDropdownTests(unittest.TestCase):
    def view(self):
        v=UpdateView.__new__(UpdateView);v.app=Mock();v.checking=v.installing=False
        v.old_loaded=v.old_loading=v.old_retry=False
        v.old_versions={};v.old_choice=Mock();v.button=Mock();v.status=Mock()
        v.jobs=queue.Queue();v.work=None;v.dialog=None;v.startup=False
        return v

    def test_first_open_fetches_once_and_shows_returned_versions(self):
        v=self.view();versions=[{'version':'1.1.3','url':'test'},{'version':'1.1.2','url':'test2'}]
        def start(*,target,daemon):
            worker=Mock();worker.start.side_effect=target;return worker
        with patch('drop_tool.update_view.threading.Thread',side_effect=start),patch.object(updater,'old_releases',return_value=versions) as fetch:
            v.ensure_old_releases();self.assertTrue(v.old_loading)
            v.poll();v.ensure_old_releases()
        fetch.assert_called_once();self.assertTrue(v.old_loaded)
        self.assertEqual(list(v.old_versions),['v1.1.3','v1.1.2'])
        v.old_choice.configure.assert_called_with(values=['v1.1.3','v1.1.2'])

    def test_startup_check_defers_single_retry_instead_of_empty_forever(self):
        v=self.view();v.checking=True;v.load_old_releases=Mock()
        v.ensure_old_releases();v.ensure_old_releases()
        v.app.root.after.assert_called_once()
        v.checking=False;v.app.root.after.call_args.args[1]()
        v.load_old_releases.assert_called_once()

    def test_no_versions_is_cached_and_error_clears_loading_for_retry(self):
        v=self.view();v.jobs.put(('old-releases',[]));v.poll()
        v.load_old_releases=Mock();v.ensure_old_releases();v.load_old_releases.assert_not_called()
        v=self.view();v.old_loading=True
        with patch('drop_tool.update_view.messagebox.showerror'):v.failed('offline')
        self.assertFalse(v.old_loading);self.assertFalse(v.old_loaded)
        v.old_choice.set.assert_called_with('旧版一覧の取得に失敗')
