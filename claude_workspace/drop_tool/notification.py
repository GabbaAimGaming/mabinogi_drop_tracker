"""読取通知専用。再生失敗で保存済みの報酬を失敗扱いにしない。"""
import json
import winsound
from .config import ROOT

# captured：ALT表示の撮影が終わった（ALTを離してよい）。complete：解析して周回に保存した。
SOUNDS = {'start': 'capture-complete.wav', 'captured': 'capture-complete.wav', 'complete': 'read-complete.wav', 'error': 'read-error.wav'}


class CompletionSound:
    def __init__(self, folder):
        self.path = folder / 'notification.json'
        try:
            self.enabled = json.loads(self.path.read_text('utf-8')).get('enabled', True) is not False
        except (OSError, ValueError, AttributeError):
            self.enabled = True

    def set_enabled(self, enabled):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'enabled': bool(enabled)}), encoding='utf-8')
        temporary.replace(self.path)
        self.enabled = bool(enabled)

    def play(self, preview=False, kind='complete'):
        """読取音を鳴らす。ON/OFFは撮影完了音・解析完了音で共通。"""
        if not (self.enabled or preview):
            return
        try:
            # 非同期再生。OS既定の警告音にはフォールバックしない。
            winsound.PlaySound(str(ROOT / 'assets' / SOUNDS[kind]),
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except (RuntimeError, OSError):
            pass
