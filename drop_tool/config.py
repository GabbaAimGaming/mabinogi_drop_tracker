"""EXE版もソース版も、利用者のデータをアプリの隣に保持する。"""
from pathlib import Path
import os
import sys


def application_root():
    """凍結版の内部ライブラリ位置へ記録を保存しない。"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


ROOT = application_root()


def configure_tk():
    """凍結版の同梱Tcl/Tkを使う。特殊フォルダの絶対パス解決の差を避ける。"""
    if not getattr(sys, 'frozen', False):
        return
    for variable, name in (('TCL_LIBRARY', '_tcl_data'), ('TK_LIBRARY', '_tk_data')):
        folder = Path(sys._MEIPASS) / name
        if folder.is_dir():
            try:
                path = os.path.relpath(folder)
            except ValueError:  # 作業フォルダが別ドライブなら絶対パスを使う。
                path = str(folder)
            os.environ[variable] = path
