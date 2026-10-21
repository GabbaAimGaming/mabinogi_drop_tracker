"""凍結版の同梱Tcl/Tk参照と、ソース実行時の既存設定保持を確認する。"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TkRuntimeTests(unittest.TestCase):
    def test_source_run_preserves_existing_tcl_settings(self):
        from drop_tool.config import configure_tk
        with patch('drop_tool.config.sys.frozen', False, create=True), patch.dict(os.environ, {'TCL_LIBRARY': 'custom'}):
            configure_tk()
            self.assertEqual(os.environ['TCL_LIBRARY'], 'custom')

    def test_frozen_run_uses_bundled_libraries_relative_to_working_folder(self):
        from drop_tool.config import configure_tk
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ('_tcl_data', '_tk_data'):(root/name).mkdir()
            with patch('drop_tool.config.sys.frozen', True, create=True), patch('drop_tool.config.sys._MEIPASS', str(root), create=True), patch.dict(os.environ):
                configure_tk()
                self.assertEqual(os.environ['TCL_LIBRARY'], os.path.relpath(root/'_tcl_data'))
                self.assertEqual(os.environ['TK_LIBRARY'], os.path.relpath(root/'_tk_data'))
