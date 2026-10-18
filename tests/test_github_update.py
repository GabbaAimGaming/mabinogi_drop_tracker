import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request
from drop_tool import updater as u
from drop_tool.tracker import Store
from drop_tool.update_view import UpdateView


class GitHubUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_migration_only_known_legacy_source(self):
        for url in ('', 'https://drive.google.com/file/d/' + u.LEGACY_FEED_ID + '/view?usp=sharing',
                    'https://drive.usercontent.google.com/download?id=' + u.LEGACY_FEED_ID):
            self.assertEqual(u.effective_source(url), u.DEFAULT_SOURCE)
        custom = 'https://drive.google.com/file/d/1234567890custom/view'
        self.assertEqual(u.effective_source(custom), custom)

    def test_official_release_urls_and_host_spoofing(self):
        for url in (u.DEFAULT_SOURCE, u.RELEASES_URL + '/download/v1.0/KarenDrop-v1.0-windows.zip'):
            self.assertEqual(u.download_url(url), url)
        for url in ('https://github.com/other/repo/releases/latest/download/update-info.json',
                    u.DEFAULT_SOURCE.replace('github.com', 'github.com.evil.test'),
                    u.DEFAULT_SOURCE.replace('https:', 'http:'),
                    u.DEFAULT_SOURCE + '?redirect=evil', u.DEFAULT_SOURCE.replace('github.com/', 'github.com@evil.test/')):
            with self.subTest(url=url), self.assertRaises(ValueError):
                u.download_url(url)

    def response(self, body, content_type='application/json', length=None):
        r = io.BytesIO(body)
        r.headers = {'Content-Type': content_type, 'Content-Length': str(len(body) if length is None else length)}
        r.geturl = lambda: 'https://release-assets.githubusercontent.com/github-production-release-asset/test?token=test'
        return r

    def test_github_download_and_manifest_validation(self):
        body = json.dumps({'schema_version': 1, 'app_id': 'KarenDrop', 'version': u.VERSION, 'package': None}).encode()
        opener = Mock(); opener.open.return_value = self.response(body)
        with patch.object(u, 'build_opener', return_value=opener):
            self.assertEqual(u.check(u.DEFAULT_SOURCE, self.root)['version'], u.VERSION)

    def test_interrupted_download_is_removed(self):
        opener = Mock(); opener.open.return_value = self.response(b'partial', length=100)
        with patch.object(u, 'build_opener', return_value=opener), self.assertRaises(ValueError):
            u.download(u.DEFAULT_SOURCE, self.root/'download', 1000)
        self.assertFalse((self.root/'download').exists())

    def test_github_html_is_not_treated_as_drive_confirmation(self):
        opener = Mock(); opener.open.return_value = self.response(b'<html>error</html>', 'text/html')
        with patch.object(u, 'build_opener', return_value=opener), self.assertRaises(ValueError):
            u.download(u.DEFAULT_SOURCE, self.root/'download', 1000)
        self.assertFalse((self.root/'download').exists())

    def test_unpublished_and_limited_release_are_not_latest(self):
        for code, message in ((404, '公開'), (403, '制限'), (429, '制限')):
            with patch.object(u, 'download', side_effect=HTTPError(u.DEFAULT_SOURCE, code, 'error', {}, None)):
                with self.assertRaisesRegex(ValueError, message):
                    u.check(u.DEFAULT_SOURCE, self.root)

    def test_cdn_redirect_and_untrusted_redirect(self):
        redirect = u.DriveRedirect()
        request = Request(u.DEFAULT_SOURCE)
        allowed = 'https://release-assets.githubusercontent.com/github-production-release-asset/123?sig=test'
        self.assertEqual(redirect.redirect_request(request, None, 302, 'Found', {}, allowed).full_url, allowed)
        with self.assertRaises(ValueError):
            redirect.redirect_request(request, None, 302, 'Found', {}, 'https://evil.test/download')

    def test_new_run_write_failure_rolls_back_and_can_retry(self):
        store = Store(self.root)
        store.new_run('アルビ', 'HD', '使用')
        original = store.path.read_bytes()
        with patch.object(Path, 'replace', side_effect=PermissionError('保存先へのアクセス拒否')):
            with self.assertRaises(PermissionError):
                store.new_run('ルンダ', 'HD', '不使用')
        self.assertEqual(len(store.data['runs']), 1)
        self.assertEqual(store.path.read_bytes(), original)
        store.new_run('ルンダ', 'HD', '不使用')
        self.assertEqual(len(Store(self.root).data['runs']), 2)

    def test_save_failure_before_update_never_stops_or_downloads(self):
        view = UpdateView.__new__(UpdateView)
        view.app = Mock(); view.app.busy = False
        view.app.samples.lock.locked.return_value = False
        view.app.store.save.side_effect = PermissionError('blocked')
        view.button = Mock(); view.failed = Mock()
        info = {'version': '2.0', 'release_notes': 'test'}
        with patch('drop_tool.update_view.messagebox.askyesno', return_value=True), patch.object(u.sys, 'frozen', True, create=True), patch.object(u, 'prepare') as prepare:
            view.offer(info)
        view.failed.assert_called_once()
        view.app.stop.assert_not_called()
        prepare.assert_not_called()
