import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from drop_tool import updater as u
from drop_tool.update_view import UpdateView


class RollbackTests(unittest.TestCase):
    def release(self, version='1.1.2', **extra):
        r = {'tag_name':'v'+version, 'assets':[{'name':'update-info.json',
             'browser_download_url':u.RELEASES_URL+'/download/v'+version+'/update-info.json'}]}
        r.update(extra)
        return r

    def test_list_ignores_newer_drafts_prereleases_and_missing_or_foreign_assets(self):
        rows = [self.release('1.0'), self.release(), self.release(u.VERSION),
                self.release('99.0'), self.release('1.1.1', draft=True),
                self.release('1.1.1', prerelease=True), self.release('1.1.1', assets=[]),
                self.release('1.1.1', assets=[{'name':'update-info.json', 'browser_download_url':'https://evil.test/x'}]),
                self.release(), self.release('garbage')]
        response = io.BytesIO(json.dumps(rows).encode()); response.geturl=lambda:u.RELEASES_API
        opener=Mock();opener.open.return_value=response
        with patch.object(u,'build_opener',return_value=opener):
            self.assertEqual([r['version'] for r in u.old_releases()], ['1.1.2','1.0'])

    def test_selected_metadata_must_match_and_have_full_package(self):
        r={'version':'1.1.2','url':u.RELEASES_URL+'/download/v1.1.2/update-info.json'}
        for info in ({'version':'1.1.1','package':{'size':1}}, {'version':'1.1.2','package':None}):
            with patch.object(u,'check',return_value=info),self.assertRaises(ValueError):
                u.check_old_release(r,Path('.'))
        with patch.object(u,'check',return_value={'version':'1.1.2','package':{'size':1}}):
            self.assertEqual(u.check_old_release(r,Path('.'))['version'],'1.1.2')

    def test_only_unchanged_manifest_files_are_removed_data_stays_outside_plan(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'assets').mkdir();(root/'data').mkdir()
            (root/'assets/new.txt').write_text('new');(root/'data/records.json').write_text('history')
            manifest={'app_id':u.APP_ID,'schema_version':1,'version':u.VERSION,
                      'files':[{'path':'assets/new.txt','sha256':u.digest(root/'assets/new.txt')}]}
            (root/'release-manifest.json').write_text(json.dumps(manifest))
            result=u.rollback_removals(root,{'files':[{'path':'KarenDrop.exe'}]})
            self.assertEqual([r['path'] for r in result],['assets/new.txt'])
            self.assertTrue(result[0]['delete_file'])
            self.assertEqual((root/'data/records.json').read_text(),'history')
            (root/'assets/new.txt').write_text('user edited')
            with self.assertRaisesRegex(ValueError,'変更'):
                u.rollback_removals(root,{'files':[]})
            manifest['files']=[{'path':'data/records.json','sha256':'0'*64}]
            (root/'release-manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):u.rollback_removals(root,{'files':[]})

    def test_decline_rollback_never_saves_stops_or_downloads(self):
        view=UpdateView.__new__(UpdateView);view.app=Mock();view.button=Mock()
        view.status=Mock();view.startup=False;view.work=Mock()
        with patch.object(u,'cleanup'),patch.object(u,'prepare') as prepare, \
             patch('drop_tool.update_view.messagebox.askyesno',return_value=False) as ask:
            view.offer({'version':'1.1.2'},rollback=True)
        self.assertIn('旧バージョン',ask.call_args.args[1])
        view.app.stop.assert_not_called();view.app.store.save.assert_not_called();prepare.assert_not_called()

    def test_rollback_cannot_install_current_or_future_version(self):
        for version in (u.VERSION,'99.0'):
            view=UpdateView.__new__(UpdateView);view.app=Mock();view.button=Mock()
            view.status=Mock();view.startup=False;view.failed=Mock()
            with patch('drop_tool.update_view.messagebox.askyesno') as ask:
                view.offer({'version':version},rollback=True)
            view.failed.assert_called_once();ask.assert_not_called()
