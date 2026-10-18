"""選んだウィンドウだけを映す「画面共有」撮影（Windows Graphics Capture）。

windows-capture（MIT）経由で、指定したHWNDの映像だけを受け取る。
他のウィンドウが重なっても、ゲーム自身の映像を読める。共有中はOSが
ウィンドウに枠を表示する（Windows 10では常に表示）。

キー入力・フック・ゲームへの書込みは一切行わない。映像を受け取るだけ。
"""
import ctypes
import threading
import time
from ctypes import wintypes

import numpy as np
from PIL import Image

# 受け取ったフレームを毎回コピーすると負荷が高いので、この間隔より短い
# フレームは捨てる（ゲームが60fpsでも約5fpsで保持）。
COPY_INTERVAL = 0.2
# これより古いフレームは「映っていない（最小化など）」として扱う。
STALE_AFTER = 2.0


class ShareUnavailable(RuntimeError):
    """画面共有から最新の映像を得られない。呼び出し側は従来撮影へ戻せる。"""


def _default_backend():
    try:
        from windows_capture import WindowsCapture
    except Exception as exc:  # DLL不足・非対応OSも含めて共有だけを無効にする
        raise ShareUnavailable('画面共有ライブラリ（windows-capture）を読み込めません：' + str(exc)) from exc
    return WindowsCapture


def client_offset(hwnd, frame_width, frame_height):
    """共有映像（枠を含むウィンドウ全体）の中の、クライアント領域の位置。

    取得できない場合は映像全体を返す。従来撮影と同じくタイトルバーを除くため。
    """
    try:
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        dwmapi = ctypes.WinDLL('dwmapi')
        bounds = wintypes.RECT()
        # DWMWA_EXTENDED_FRAME_BOUNDS = 9。Graphics Captureの映像はこの範囲。
        if dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(bounds), ctypes.sizeof(bounds)):
            raise OSError('DwmGetWindowAttribute')
        client = wintypes.RECT()
        origin = wintypes.POINT(0, 0)
        if not user32.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(client)) or \
                not user32.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(origin)):
            raise OSError('GetClientRect')
        left = origin.x - bounds.left
        top = origin.y - bounds.top
        width, height = client.right, client.bottom
    except (OSError, AttributeError, TypeError, ValueError):
        return 0, 0, frame_width, frame_height
    left = min(max(0, int(left)), frame_width)
    top = min(max(0, int(top)), frame_height)
    right = min(frame_width, left + max(0, int(width)))
    bottom = min(frame_height, top + max(0, int(height)))
    if right - left < 50 or bottom - top < 50:
        return 0, 0, frame_width, frame_height
    return left, top, right, bottom


class WindowShare:
    """1つのウィンドウの共有セッション。フレームは別スレッドで届き、最新1枚だけ保持する。"""

    def __init__(self, hwnd, name='', backend=None, offset=client_offset, clock=time.monotonic):
        self.hwnd = int(hwnd)
        self.name = name
        self._backend = backend
        self._offset = offset
        self._clock = clock
        self._lock = threading.Lock()
        self._frame = None
        self._frame_time = None
        self._control = None
        self.closed = False
        self.error = ''
        self.frames = 0

    @property
    def running(self):
        return self._control is not None and not self.closed

    def start(self):
        backend = self._backend or _default_backend()
        try:
            capture = backend(cursor_capture=False, draw_border=None, window_hwnd=self.hwnd)
        except Exception as exc:
            raise ShareUnavailable('このウィンドウは画面共有で撮影できません：' + str(exc)) from exc

        share = self

        @capture.event
        def on_frame_arrived(frame, capture_control):
            share._receive(frame)

        @capture.event
        def on_closed():
            share.closed = True

        try:
            self._control = capture.start_free_threaded()
        except Exception as exc:
            raise ShareUnavailable('画面共有を開始できません：' + str(exc)) from exc
        return self

    def _receive(self, frame):
        now = self._clock()
        if self._frame_time is not None and now - self._frame_time < COPY_INTERVAL:
            return
        try:
            buffer = np.asarray(frame.frame_buffer)
            height, width = int(frame.height), int(frame.width)
            # BGRA → RGB。元のバッファはコールバック後に再利用されるため必ず複製する。
            rgb = np.ascontiguousarray(buffer[:height, :width, 2::-1])
        except Exception as exc:
            self.error = '映像の形式を読めません：' + str(exc)
            return
        with self._lock:
            self._frame = rgb
            self._frame_time = now
            self.frames += 1

    def frame(self, region=None):
        """最新の映像をクライアント領域で切り出して返す。regionは0～1の比率(x0,y0,x1,y1)。"""
        with self._lock:
            rgb, stamp = self._frame, self._frame_time
        if self.closed:
            raise ShareUnavailable('共有中のウィンドウが閉じられました。')
        if rgb is None:
            raise ShareUnavailable('画面共有の映像をまだ受信していません。')
        if self._clock() - stamp > STALE_AFTER:
            raise ShareUnavailable('画面共有の映像が更新されていません（最小化中の可能性）。')
        height, width = rgb.shape[:2]
        left, top, right, bottom = self._offset(self.hwnd, width, height)
        if region is not None:
            w, h = right - left, bottom - top
            x0, y0, x1, y1 = region
            left, top, right, bottom = (left + round(w * x0), top + round(h * y0),
                                        left + round(w * x1), top + round(h * y1))
        return Image.fromarray(rgb[top:bottom, left:right])

    def stop(self):
        control, self._control = self._control, None
        if control is not None:
            try:
                control.stop()
            except Exception:
                pass
        with self._lock:
            self._frame = None
            self._frame_time = None
