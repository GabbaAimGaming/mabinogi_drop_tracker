"""実Windows mutexで別プロセスからの多重起動と異常終了後の再取得を確認。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
if sys.platform != 'win32':
    raise unittest.SkipTest('Windowsのmutexを使うためWindows専用')
from drop_tool.instance_guard import InstanceGuard, identity

CHILD = '''
import sys
from drop_tool.instance_guard import InstanceGuard
g=InstanceGuard(sys.argv[1],sys.argv[2])
ok=g.acquire()
print('yes' if ok else 'no',flush=True)
if ok and len(sys.argv)>3: sys.stdin.readline()
g.close()
'''

class InstanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))

    def probe(self, exe, data):
        p = subprocess.run([sys.executable, '-c', CHILD, str(exe), str(data)],
                           env=self.env, capture_output=True, text=True, timeout=15,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.strip() == 'yes'

    def test_same_executable_or_data_blocked_separate_copy_allowed(self):
        a, b = self.base/'a/KarenDrop.exe', self.base/'b/KarenDrop.exe'
        data = self.base/'a/data'
        guard = InstanceGuard(a, data)
        self.addCleanup(guard.close)
        self.assertTrue(guard.acquire())
        self.assertFalse(self.probe(a, data))
        self.assertFalse(self.probe(a, self.base/'different-data'))
        self.assertFalse(self.probe(b, data))
        self.assertTrue(self.probe(b, self.base/'b/data'))
        guard.close()
        self.assertTrue(self.probe(a, data))

    def test_terminated_owner_does_not_leave_stale_lock(self):
        exe, data = self.base/'KarenDrop.exe', self.base/'data'
        p = subprocess.Popen([sys.executable,'-c',CHILD,str(exe),str(data),'hold'],
                             env=self.env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.assertEqual(p.stdout.readline().strip(),'yes')
            self.assertFalse(self.probe(exe,data))
            p.kill();p.wait(timeout=10)
            self.assertTrue(self.probe(exe,data))
        finally:
            if p.poll() is None:p.kill();p.wait(timeout=10)
            p.stdin.close();p.stdout.close();p.stderr.close()

    def test_path_case_and_relative_components(self):
        path=self.base/'KarenDrop.exe'
        self.assertEqual(identity('exe',path),identity('exe',str(path).upper()))
        self.assertEqual(identity('exe',path),identity('exe',self.base/'x/../KarenDrop.exe'))

