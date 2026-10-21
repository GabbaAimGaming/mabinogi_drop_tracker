"""tools/run_tests.pyのテスト名による絞り込み。"""
from pathlib import Path
import re
import os
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / 'tools' / 'run_tests.py'
TARGET = 'test_learning'


def run(*args):
    return subprocess.run([sys.executable, str(RUNNER), *args], cwd=ROOT, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                          capture_output=True, text=True, encoding='utf-8', timeout=300)


def ran(result):
    found = re.search(r'Ran (\d+) tests?', result.stderr)
    return int(found.group(1)) if found else None


class RunTestsSelectionTests(unittest.TestCase):
    def test_module_name_runs_only_that_module(self):
        expected = unittest.defaultTestLoader.loadTestsFromName(TARGET).countTestCases()
        result = run(TARGET)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(ran(result), expected)

    def test_path_and_method_names_are_accepted(self):
        by_name = run(TARGET)
        by_path = run(f'tests/{TARGET}.py')
        self.assertEqual(by_path.returncode, 0, by_path.stderr)
        self.assertEqual(ran(by_path), ran(by_name))
        method = 'test_learning.LearningTests.test_normal_correction_learns_official_name_and_duplicate_does_not_grow'
        one = run(method)
        self.assertEqual(one.returncode, 0, one.stderr)
        self.assertEqual(ran(one), 1)

    def test_unknown_name_fails_without_running(self):
        for name in ('test_does_not_exist', 'test_learning.NoSuchClass'):
            with self.subTest(name=name):
                result = run(name)
                self.assertEqual(result.returncode, 1)
                self.assertIn('テストを読み込めませんでした', result.stderr)
                self.assertIsNone(ran(result))


if __name__ == '__main__':
    unittest.main()
