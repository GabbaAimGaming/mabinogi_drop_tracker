import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile
from drop_tool import updater as u
from drop_tool.update_view import UpdateView

URL = 'https://drive.google.com/file/d/1234567890abc/view?usp=sharing'


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def package(self, version='0.18.2', extra=None):
        files = {'KarenDrop.exe':b'new executable', 'update_helper.ps1':b'helper', 'assets/test.txt':b'asset'}
        if extra: files.update(extra)
        manifest = {'schema_version':1, 'app_id':'KarenDrop', 'version':version,
                    'files':[{'path':n, 'sha256':hashlib.sha256(b).hexdigest()} for n,b in files.items()]}
        p = self.root/'update.zip'
        with ZipFile(p, 'w') as z:
            for n,b in files.items(): z.writestr('KarenDrop/'+n, b)
            z.writestr('KarenDrop/release-manifest.json', json.dumps(manifest))
        info = {'schema_version':1,'app_id':'KarenDrop','version':version,'package':{'url':URL,'sha256':u.digest(p),'size':p.stat().st_size}}
        work = u.new_work(self.root)
        return p, info, work

    def test_version_uses_numbers_not_text(self):
        self.assertGreater(u.version_key('0.20'), u.version_key('0.19.9'))
        self.assertGreater(u.version_key('0.18.1'), u.version_key('0.18'))
        self.assertEqual(u.version_key('1.0'), u.version_key('1.0.0'))
        for bad in ('v0.19', '0.19-beta', None):
            with self.assertRaises(ValueError): u.version_key(bad)

    def test_drive_ids_and_resource_keys(self):
        self.assertIn('id=1234567890abc', u.drive_url(URL))
        self.assertIn('resourcekey=0-abc', u.drive_url(URL+'&resourcekey=0-abc'))
        for bad in ('http://drive.google.com/open?id=1234567890', 'https://evil.test/open?id=1234567890', 'https://drive.google.com/drive/folders/1234567890', 'https://drive.google.com@evil.test/open?id=1234567890'):
            with self.assertRaises(ValueError): u.drive_url(bad)

    def test_full_package_stages_without_user_data(self):
        (self.root/'data').mkdir(); (self.root/'data/records.json').write_text('keep')
        (self.root/'exclusions.json').write_text('personal')
        p, info, work = self.package()
        plan = u.stage(p, info, work)
        self.assertEqual((Path(plan['payload'])/'KarenDrop.exe').read_bytes(), b'new executable')
        self.assertEqual((self.root/'data/records.json').read_text(), 'keep')
        self.assertEqual((self.root/'exclusions.json').read_text(), 'personal')
        u.cleanup(work, self.root)
        self.assertFalse(work.exists())

    def test_bad_hash_and_wrong_version_do_not_stage(self):
        p, info, work = self.package()
        info['package']['sha256']='0'*64
        with self.assertRaises(ValueError): u.stage(p, info, work)
        self.assertFalse((work/'payload').exists())
        info=u.make_info(p,URL);info['version']='0.19'
        with self.assertRaises(ValueError): u.stage(p, info, work)

    def test_protected_files_and_traversal_are_rejected(self):
        for bad in ('data/records.json','exclusions.json','assets/../../data/records.json','assets/a:b','/KarenDrop.exe','assets/NUL','assets/a./b','assets\\x'):
            with self.subTest(bad=bad):
                p,info,work=self.package(extra={bad:b'bad'})
                with self.assertRaises(ValueError): u.stage(p,info,work)
                self.assertFalse((work/'payload').exists())

    def test_unrelated_folder_is_not_cleaned(self):
        p=self.root/'user';p.mkdir();(p/'keep').write_text('keep')
        u.cleanup(p,self.root)
        self.assertTrue((p/'keep').exists())

    def test_payload_hash_checked(self):
        p,info,work=self.package()
        with ZipFile(p,'a') as z: z.writestr('KarenDrop/assets/test.txt',b'changed')
        info=u.make_info(p,URL)
        with self.assertRaises(ValueError): u.stage(p,info,work)

    def test_manifest_schema(self):
        _, info, _=self.package()
        self.assertEqual(u.validate_info(info)['version'],'0.18.2')
        info['app_id']='other'
        with self.assertRaises(ValueError): u.validate_info(info)

    def test_initial_feed_has_no_download_and_future_missing_zip_fails(self):
        info={'schema_version':1,'app_id':'KarenDrop','version':u.VERSION,'package':None}
        self.assertEqual(u.validate_info(info),info)
        info['version']='99.0'
        with self.assertRaises(ValueError):u.validate_info(info)

    def response(self, body, content_type):
        response=io.BytesIO(body)
        response.headers={'Content-Type':content_type,'Content-Length':str(len(body))}
        response.geturl=lambda: u.drive_url(URL)
        return response

    def test_drive_confirmation_then_download(self):
        html=b'<form id="download-form" action="https://drive.usercontent.google.com/download"><input name="id" value="1234567890abc"><input name="confirm" value="t"></form>'
        opener=Mock();opener.open.side_effect=[self.response(html,'text/html'),self.response(b'ZIP','application/zip')]
        with patch.object(u,'build_opener',return_value=opener):
            u.download(URL,self.root/'zip',100)
        self.assertEqual((self.root/'zip').read_bytes(),b'ZIP')

    def test_login_html_and_oversized_download_fail(self):
        for body,typ,limit in [(b'<html>login</html>','text/html',100),(b'big','application/zip',1)]:
            opener=Mock();opener.open.return_value=self.response(body,typ)
            with patch.object(u,'build_opener',return_value=opener):
                with self.assertRaises(ValueError): u.download(URL,self.root/'zip',limit)
            self.assertFalse((self.root/'zip').exists())

    def test_cancel_does_not_prepare_or_stop_application(self):
        _,info,work=self.package(version='9999.0')
        view=UpdateView.__new__(UpdateView);view.app=Mock();view.button=Mock();view.status=Mock();view.work=work
        with patch('drop_tool.update_view.messagebox.askyesno',return_value=False),patch('drop_tool.update_view.ROOT',self.root),patch.object(u,'prepare') as prepare:
            view.offer(info)
        view.app.stop.assert_not_called();prepare.assert_not_called()

    def test_current_version_does_not_offer_installation(self):
        _,info,work=self.package(version=u.VERSION)
        view=UpdateView.__new__(UpdateView);view.app=Mock();view.button=Mock();view.status=Mock();view.work=work
        with patch('drop_tool.update_view.messagebox.showinfo') as show,patch('drop_tool.update_view.messagebox.askyesno') as ask,patch('drop_tool.update_view.ROOT',self.root):
            view.offer(info)
        ask.assert_not_called();self.assertIn('最新版',show.call_args.args[1])
