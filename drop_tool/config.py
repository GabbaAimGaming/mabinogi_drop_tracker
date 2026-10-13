"""EXE版もソース版も、利用者のデータをアプリの隣に保持する。"""
from pathlib import Path
import sys


def application_root():
    """凍結版の内部ライブラリ位置へ記録を保存しない。"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


ROOT = application_root()
