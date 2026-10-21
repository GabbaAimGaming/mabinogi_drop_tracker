"""本体と分離したテストをソースルートから実行する。

使い方：
  python tools/run_tests.py                      全量（tests/を探索）
  python tools/run_tests.py test_learning        モジュールを指定（複数可）
  python tools/run_tests.py test_learning.LearningTests.test_xxx   クラス・メソッドまで指定
  python tools/run_tests.py tests/test_learning.py                 パスでも指定できる
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
import _headless
_headless.install()  # tkinter等が無い環境だけ代役を入れる。Windowsでは何もしない。


def module_name(arg):
    """`tests/test_x.py`や`test_x.py`をモジュール名`test_x`へ直す。それ以外はそのまま返す。"""
    if arg.endswith('.py'):
        return Path(arg).stem
    return arg


def load(args):
    """引数が無ければ全量、あれば指定した名前だけ読む。読み込めなかった名前は一覧で返す。"""
    loader = unittest.defaultTestLoader
    if not args:
        return loader.discover(str(ROOT / 'tests')), []
    suite, missing = unittest.TestSuite(), []
    for arg in args:
        name = module_name(arg)
        try:
            suite.addTest(loader.loadTestsFromName(name))
        except (ImportError, AttributeError) as error:
            missing.append(f'{arg}（{error}）')
    # 読み込み時の失敗はloaderが_FailedTestとして記録する場合もある
    for error in loader.errors:
        missing.append(error.strip().splitlines()[-1])
    return suite, missing


def main(args):
    suite, missing = load(args)
    if missing:
        print('テストを読み込めませんでした（名前の誤り、またはimportの失敗）：', file=sys.stderr)
        for item in missing:
            print('  ' + item, file=sys.stderr)
        return 1
    return int(not unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful())


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
