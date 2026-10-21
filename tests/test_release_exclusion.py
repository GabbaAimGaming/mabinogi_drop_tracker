"""リリースに含めないフォルダー（claude_workspace）の混入防止を確認する。"""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def load_package_release():
    spec = importlib.util.spec_from_file_location('package_release_under_test', ROOT / 'tools' / 'package_release.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_release_folder(base):
    """配布フォルダーの最小構成。実際の資産は使わない。"""
    folder = Path(base) / 'KarenDrop'
    (folder / 'assets').mkdir(parents=True)
    (folder / 'assets' / 'sample.txt').write_text('sample', 'utf-8')
    (folder / 'README_EXE.txt').write_text('readme', 'utf-8')
    (folder / '更新内容.txt').write_text('notes', 'utf-8')
    return folder


class ReleaseExclusionTest(unittest.TestCase):
    def setUp(self):
        self.module = load_package_release()

    def test_workspace_is_excluded_and_not_whitelisted(self):
        self.assertIn('claude_workspace', self.module.RELEASE_EXCLUDED_DIRS)
        self.assertNotIn('claude_workspace', self.module.TOP_DIRS)
        self.assertNotIn('claude_workspace', self.module.TOP_FILES)

    def test_clean_folder_packages_without_workspace(self):
        with tempfile.TemporaryDirectory() as base:
            folder = make_release_folder(base)
            output = Path(base) / 'out.zip'
            self.module.package(folder, output)
            with ZipFile(output) as z:
                names = z.namelist()
            self.assertIn('KarenDrop/README_EXE.txt', names)
            self.assertFalse([n for n in names if 'claude_workspace' in n])

    def test_top_level_workspace_stops_packaging(self):
        with tempfile.TemporaryDirectory() as base:
            folder = make_release_folder(base)
            (folder / 'claude_workspace').mkdir()
            (folder / 'claude_workspace' / 'CLAUDE.md').write_text('x', 'utf-8')
            output = Path(base) / 'out.zip'
            with self.assertRaises(ValueError):
                self.module.package(folder, output)
            self.assertFalse(output.exists())
            # 混入時はmanifestも書かない。
            self.assertFalse((folder / 'release-manifest.json').exists())

    def test_nested_workspace_stops_packaging(self):
        with tempfile.TemporaryDirectory() as base:
            folder = make_release_folder(base)
            nested = folder / 'assets' / 'claude_workspace'
            nested.mkdir()
            (nested / 'x.txt').write_text('x', 'utf-8')
            with self.assertRaises(ValueError):
                self.module.package(folder, Path(base) / 'out.zip')

    def test_zip_is_discarded_when_workspace_leaks_past_folder_check(self):
        """許可リストと事前確認の両方が破られた場合でも、ZIPの最終確認で止める。"""
        with tempfile.TemporaryDirectory() as base:
            folder = make_release_folder(base)
            (folder / 'claude_workspace').mkdir()
            (folder / 'claude_workspace' / 'CLAUDE.md').write_text('x', 'utf-8')
            output = Path(base) / 'out.zip'
            with mock.patch.object(self.module, 'TOP_DIRS', set(self.module.TOP_DIRS) | {'claude_workspace'}), \
                    mock.patch.object(self.module, 'forbidden_paths', return_value=[]):
                with self.assertRaises(ValueError):
                    self.module.package(folder, output)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
