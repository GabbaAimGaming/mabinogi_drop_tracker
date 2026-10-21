"""tkinter・winsoundの無い環境（Linux等）で、ロジック系テストを実行するための代役。

本体のコードは変更しない。実物を読み込めない時だけsys.modulesへ代役を入れる。
- 画面を実際に作る処理（tk.Tk()等）はSkipTestになり、成功扱いにはならない。
- テストがpatchする属性（messagebox.askyesno、winsound.PlaySound等）は存在するので、
  patch済みの呼び出しはそのまま検証できる。patchされていない呼び出しもSkipTestにする。
Windowsでは実物が読み込めるため何もしない。
"""
import sys
import types
import unittest


def _unavailable(name):
    def call(*args, **kwargs):
        raise unittest.SkipTest(f'{name}はこの環境で使えません')
    call.__name__ = name.rsplit('.', 1)[-1]
    return call


def _module(name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    # 定数（END、SND_ASYNC等）は値、それ以外は呼ぶとSkipTestになる代役を返す。
    module.__getattr__ = lambda attr: (0 if attr.isupper() else _unavailable(f'{name}.{attr}'))
    return module


def _install_tkinter():
    try:
        import tkinter  # noqa: F401
        return
    except ImportError:
        pass

    class TclError(Exception):
        pass

    class Unavailable(TclError, unittest.SkipTest):
        """tk.TclErrorを捕まえてskipするテストと、捕まえないテストの両方でskipにする。"""

    def widget(name):
        def init(self, *args, **kwargs):
            raise Unavailable(f'tkinter.{name}はこの環境で使えません')
        return type(name, (), {'__init__': init})

    tk_names = ('Tk', 'Toplevel', 'Frame', 'Label', 'Button', 'Entry', 'Text', 'Canvas', 'Listbox',
                'Scrollbar', 'Checkbutton', 'Radiobutton', 'Menu', 'Misc', 'Widget', 'PhotoImage',
                'Variable', 'StringVar', 'IntVar', 'BooleanVar', 'DoubleVar')
    ttk_names = ('Frame', 'Label', 'Button', 'Entry', 'Combobox', 'Treeview', 'Notebook', 'Scrollbar',
                 'Checkbutton', 'Radiobutton', 'Progressbar', 'Style', 'Separator', 'LabelFrame')
    messagebox = _module('tkinter.messagebox')
    filedialog = _module('tkinter.filedialog')
    ttk = _module('tkinter.ttk', **{n: widget(n) for n in ttk_names})
    tkinter = _module('tkinter', TclError=TclError, messagebox=messagebox, filedialog=filedialog,
                      ttk=ttk, TkVersion=8.6, TclVersion=8.6, **{n: widget(n) for n in tk_names})
    tkinter.__path__ = []
    sys.modules.update({'tkinter': tkinter, 'tkinter.ttk': ttk,
                        'tkinter.messagebox': messagebox, 'tkinter.filedialog': filedialog})


def _install_winsound():
    try:
        import winsound  # noqa: F401
    except ImportError:
        sys.modules['winsound'] = _module('winsound')


def _install_windll():
    """windows_captureが読み込み時にuser32を準備するため、属性設定だけ受け付ける代役。"""
    import ctypes
    if hasattr(ctypes, 'WinDLL'):
        return

    class Function:
        def __init__(self, name):
            self.__name__ = name

        def __call__(self, *args, **kwargs):
            raise unittest.SkipTest(f'{self.__name__}はWindows専用です')

    class WinDLL:
        def __init__(self, name, *args, **kwargs):
            self._name = name

        def __getattr__(self, attr):
            function = Function(f'{self._name}.{attr}')
            setattr(self, attr, function)
            return function

    ctypes.WinDLL = WinDLL
    ctypes.WINFUNCTYPE = _unavailable('ctypes.WINFUNCTYPE')
    ctypes.get_last_error = _unavailable('ctypes.get_last_error')


def install():
    _install_tkinter()
    _install_winsound()
    _install_windll()
