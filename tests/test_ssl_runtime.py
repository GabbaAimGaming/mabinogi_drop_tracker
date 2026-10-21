"""証明書の信頼設定を保ったまま、SSL実装固有の必要ファイルを同梱する。"""
import tempfile
import unittest
from pathlib import Path

from tools.ssl_runtime import runtime_data


class SSLRuntimeTests(unittest.TestCase):
    def test_standard_runtime_needs_no_extra_file(self):
        with tempfile.TemporaryDirectory() as folder:
            module = Path(folder) / 'ssl.py'
            module.write_text('class SSLContext: pass\n', encoding='utf-8')
            self.assertEqual(runtime_data(module), [])

    def test_required_certificate_is_placed_next_to_frozen_ssl(self):
        with tempfile.TemporaryDirectory() as folder:
            module = Path(folder) / 'ssl.py'
            module.write_text("load_verify_locations(cafile='codex-rejected-cas.pem')", encoding='utf-8')
            certificate = Path(folder) / 'codex-rejected-cas.pem'
            certificate.write_bytes(b'unchanged runtime trust configuration')
            before = certificate.read_bytes()
            self.assertEqual(runtime_data(module), [(str(certificate), '.')])
            self.assertEqual(certificate.read_bytes(), before)

    def test_missing_required_file_stops_build(self):
        with tempfile.TemporaryDirectory() as folder:
            module = Path(folder) / 'ssl.py'
            module.write_text("required = 'codex-rejected-cas.pem'", encoding='utf-8')
            with self.assertRaises(FileNotFoundError):
                runtime_data(module)
