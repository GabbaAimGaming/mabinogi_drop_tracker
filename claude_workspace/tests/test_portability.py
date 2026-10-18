"""他PCへの配布準備とOCR通信の失敗経路を、インストールせずに確認する。"""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import bootstrap
from drop_tool.preflight import check_assets


class PortabilityTests(unittest.TestCase):
    def test_child_environment_drops_foreign_tk_settings_only(self):
        with patch.dict(os.environ, {'TCL_LIBRARY': 'foreign', 'PYTHONPATH': 'foreign',
                                    'KEEP_USER_SETTING': 'keep'}):
            clean = bootstrap.clean_environment()
            self.assertNotIn('TCL_LIBRARY', clean)
            self.assertNotIn('PYTHONPATH', clean)
            self.assertEqual(clean['KEEP_USER_SETTING'], 'keep')
            self.assertEqual(os.environ['TCL_LIBRARY'], 'foreign')

    def test_present_but_broken_interpreter_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'python.exe'
            file.touch()
            with patch('bootstrap.run', side_effect=OSError('broken')):
                self.assertFalse(bootstrap.healthy_python(file))

    def test_assets_report_missing_image(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'references').mkdir()
            (root / 'references/labels.json').write_text('[{"path":"missing.png"}]')
            with self.assertRaisesRegex(ValueError, 'missing.png'):
                check_assets(root)

    def test_assets_report_malformed_custom_exclusions_without_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'references').mkdir()
            (root / 'references/labels.json').write_text('[]')
            config = root / 'exclusions.json'
            config.write_text('{invalid')
            with self.assertRaises(json.JSONDecodeError):
                check_assets(root)
            self.assertEqual(config.read_text(), '{invalid')

