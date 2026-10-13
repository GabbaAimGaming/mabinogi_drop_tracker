"""Read-only capture of a user-selected foreground window, including other monitors."""
import ctypes
from ctypes import wintypes
from PIL import ImageGrab
user32 = ctypes.WinDLL('user32', use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]

def configure_dpi():
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except AttributeError:
        user32.SetProcessDPIAware()

def title(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, len(buf))
    return buf.value

def game_window(found, foreground=None):
    """完全一致のゲームタイトルを優先し、ブラウザーや補助ツールを避ける。"""
    matches = [hwnd for hwnd, name in found if name.strip().casefold() in ('マビノギ', 'mabinogi')]
    if foreground in matches:
        return foreground
    return matches[0] if matches else None

def windows():
    found = []
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback
    def visit(hwnd, param):
        name = title(hwnd)
        if name and user32.IsWindowVisible(hwnd) and ('ドロップ記録' not in name):
            found.append((int(hwnd), name))
        return True
    user32.EnumWindows.argtypes = [callback, wintypes.LPARAM]
    user32.EnumWindows(visit, 0)
    return sorted(found, key=lambda x: ('mabinogi' not in x[1].lower() and 'マビノギ' not in x[1], x[1]))

def active(hwnd):
    return bool(hwnd and user32.IsWindow(hwnd) and (not user32.IsIconic(hwnd)) and (user32.GetForegroundWindow() == hwnd))

def capture(hwnd):
    """手前にある選択ゲームのクライアント領域だけを取得する。"""
    if not active(hwnd):
        raise ValueError('選択したゲーム画面を手前にしてください。')
    rect = wintypes.RECT()
    origin = wintypes.POINT(0, 0)
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)) or not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise OSError('ゲーム画面の位置を取得できません。')
    if rect.right < 50 or rect.bottom < 50:
        raise ValueError('ゲーム画面が小さすぎます。')
    box = (origin.x, origin.y, origin.x + rect.right, origin.y + rect.bottom)
    return ImageGrab.grab(bbox=box, all_screens=True).convert('RGB')
