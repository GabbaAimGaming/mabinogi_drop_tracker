"""利用者用ZIPに旧配布者向けファイルが紛れないことを確認する。"""
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from tools.package_release import package


class ReleaseContentsTests(unittest.TestCase):
    def test_legacy_publisher_files_are_excluded_even_if_left_in_build_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'KarenDrop'
            root.mkdir()
            for name in ('KarenDrop.exe', '更新内容.txt', 'exclusions.json',
                         'update-source.json', '配布者向け更新手順.txt', '更新情報-初期登録用.json'):
                (root / name).write_text('test', encoding='utf-8')
            archive = Path(folder) / 'release.zip'
            package(root, archive)
            with ZipFile(archive) as z:
                names = z.namelist()
            self.assertNotIn('KarenDrop/配布者向け更新手順.txt', names)
            self.assertNotIn('KarenDrop/更新情報-初期登録用.json', names)
            self.assertIn('KarenDrop/update-source.json', names)
            self.assertIn('KarenDrop/release-manifest.json', names)
