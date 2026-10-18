"""本体と分離したテストをソースルートから実行する。"""
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
raise SystemExit(not unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful())
