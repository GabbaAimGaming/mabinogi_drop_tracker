"""他PCへの配布準備とOCR通信の失敗経路を、インストールせずに確認する。"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
import bootstrap
from drop_tool import ocr_engine
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

    def test_missing_powershell_has_clear_error(self):
        with patch('drop_tool.ocr_engine.shutil.which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'powershell.exe'):
                ocr_engine.probe()

    def test_ocr_error_preserves_underlying_cause(self):
        result = subprocess.CompletedProcess([], 1, b'', 'Access denied'.encode())
        with patch('drop_tool.ocr_engine.shutil.which', return_value='powershell.exe'), \
                patch('drop_tool.ocr_engine.subprocess.run', return_value=result):
            with self.assertRaisesRegex(RuntimeError, 'Access denied'):
                ocr_engine.probe()

    def test_ocr_timeout_has_clear_error(self):
        with patch('drop_tool.ocr_engine.shutil.which', return_value='powershell.exe'), \
                patch('drop_tool.ocr_engine.subprocess.run',
                      side_effect=subprocess.TimeoutExpired('powershell', 35)):
            with self.assertRaisesRegex(RuntimeError, '35秒'):
                ocr_engine.probe()

    def test_many_labels_are_batched_in_order(self):
        images = [Image.new('RGB', (100, 14), 'black') for _ in range(23)]
        calls = []
        def recognize(arguments):
            with Image.open(arguments[1]) as atlas:
                count = atlas.height // 100
                self.assertLessEqual(count, 10)
            start = sum(calls)
            calls.append(count)
            return [{'text': f'素材{start+i}', 'words': [{'y': i*100+10}]} for i in range(count)]
        with patch('drop_tool.ocr_engine.invoke', side_effect=recognize):
            names = ocr_engine.suggestions(images)
        self.assertEqual(calls, [10, 10, 3])
        self.assertEqual(names, [f'素材{i}' for i in range(23)])

    def test_large_label_does_not_overwrite_next_row(self):
        atlas, height = ocr_engine.make_atlas([Image.new('RGB', (200, 40))] * 2)
        self.assertEqual(height, 140)
        self.assertEqual(atlas.size, (620, 280))

    def test_empty_input_does_not_start_ocr(self):
        with patch('drop_tool.ocr_engine.invoke') as invoke:
            self.assertEqual(ocr_engine.suggestions([]), [])
            invoke.assert_not_called()
