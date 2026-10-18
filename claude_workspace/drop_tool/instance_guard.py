"""同じ実行ファイルまたは保存先の多重起動をWindowsのmutexで防ぐ。"""
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path

kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel.CreateMutexW.restype = wintypes.HANDLE
kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel.WaitForSingleObject.restype = wintypes.DWORD
kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
kernel.CloseHandle.argtypes = [wintypes.HANDLE]


def identity(kind, path):
    # resolveはショートカットの起動先、相対パス、junctionなどの表記差を解消する。
    normalized = os.path.normcase(str(Path(path).resolve()))
    return 'KarenDrop.' + hashlib.sha256((kind + ':' + normalized).encode('utf-8')).hexdigest()


class InstanceGuard:
    def __init__(self, executable, data_folder):
        self.tokens = sorted({identity('exe', executable), identity('data', data_folder)})
        self.handles = []
        self.conflict = None

    def acquire(self):
        if self.handles:
            raise RuntimeError('起動ロックは取得済みです。')
        self.conflict = None
        try:
            for token in self.tokens:
                handle = kernel.CreateMutexW(None, False, 'Global\\' + token)
                if not handle:
                    raise ctypes.WinError(ctypes.get_last_error())
                result = kernel.WaitForSingleObject(handle, 0)
                if result in (0, 0x80):  # 正常取得／以前のプロセスが異常終了
                    self.handles.append(handle)
                else:
                    error = ctypes.get_last_error()
                    kernel.CloseHandle(handle)
                    if result != 0x102:
                        raise ctypes.WinError(error)
                    self.conflict = token
                    self.close()
                    return False
            return True
        except Exception:
            self.close()
            raise

    def close(self):
        for handle in reversed(self.handles):
            kernel.ReleaseMutex(handle)
            kernel.CloseHandle(handle)
        self.handles.clear()

    def mark_window(self, root):
        user = ctypes.WinDLL('user32', use_last_error=True)
        user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user.GetAncestor.restype = wintypes.HWND
        user.SetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.HANDLE]
        root.update_idletasks()
        hwnd = user.GetAncestor(root.winfo_id(), 2)
        for token in self.tokens:
            user.SetPropW(hwnd, token, 1)

    def activate_existing(self):
        """表示はベストエフォート。前面化できなくても2つ目は起動しない。"""
        user = ctypes.WinDLL('user32', use_last_error=True)
        user.GetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
        user.GetPropW.restype = wintypes.HANDLE
        user.IsIconic.argtypes = [wintypes.HWND]
        user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user.SetForegroundWindow.argtypes = [wintypes.HWND]
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        found = []
        @callback_type
        def visit(hwnd, _):
            if user.GetPropW(hwnd, self.conflict):
                if user.IsIconic(hwnd):
                    user.ShowWindow(hwnd, 9)
                user.SetForegroundWindow(hwnd)
                found.append(hwnd)
                return False
            return True
        user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user.EnumWindows(visit, 0)
        return bool(found)
