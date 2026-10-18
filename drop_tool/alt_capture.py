"""ALTを押している間だけ出る品名表示を、表示中に連写して後から読む。

録画（2026-10-14）では、ALTを押していた時間は約1.4秒。品名板は半透明で、
1フレームごとに読み結果が揺れる。未登録名のOCRは1フレーム0.3～1秒かかるため、
「読んでは比べる」方式では表示中に3回読み終わらず、記録できなかった。

そこで次の2段階に分ける。
1. 撮影：品名板の列（alt_display.quick_check）が見えている間、軽い撮影だけを
   約0.15秒ごとに繰り返し、最大6枚を保持する。表示が2回続けて見えなくなったら終了。
2. 読取：保持したフレームから最大4枚を等間隔に選んで解析し、品名板の位置ごとの
   多数決（tracker.consensus）で1つの一覧にまとめる。ALTを離した後でも読める。

キー入力は一切読まない。画面の表示だけで判断する。
"""
import time

from .alt_display import quick_check
from .tracker import consensus

MAX_FRAMES = 6
READ_FRAMES = 4
INTERVAL = 0.15
MISSES_TO_STOP = 2
TIME_LIMIT = 8.0


def collect(grab, check=quick_check, *, first=None, clock=time.monotonic, sleep=time.sleep,
            max_frames=MAX_FRAMES, interval=INTERVAL):
    """品名表示が見えている間フレームを集める。firstは既に撮影・判定済みの1枚目。"""
    frames = [first] if first is not None else []
    misses = 0
    started = clock()
    while len(frames) < max_frames and clock() - started < TIME_LIMIT:
        sleep(interval)
        try:
            frame = grab()
        except (OSError, ValueError, RuntimeError):
            # ゲームが背面に回った・閉じたなど。集めた分だけで読む。
            break
        if check(frame):
            frames.append(frame)
            misses = 0
        else:
            misses += 1
            if misses >= MISSES_TO_STOP:
                break
    return frames


def pick(frames, count=READ_FRAMES):
    """先頭から末尾まで等間隔に選ぶ。表示の出始め・消え際の揺れを1枚に偏らせない。"""
    if len(frames) <= count:
        return list(frames)
    step = (len(frames) - 1) / (count - 1)
    return [frames[round(i * step)] for i in range(count)]


def read(analyze, frames):
    """選んだフレームを解析し、多数決の一覧を返す。どれも読めなければ空の結果。"""
    readings = []
    analysis = []
    for index, frame in enumerate(pick(frames)):
        result = analyze(frame)
        analysis.append({'analysis_index':index,'rows':len(result.get('labels',[])),
                         'message':result.get('message','')})
        if result.get('labels'):
            readings.append(result)
    if not readings:
        return {'labels': [], 'message': 'ALT表示（品名の黒い板）が見つかりません。', 'frame_analysis':analysis,'frames':len(frames)}
    merged = consensus(readings) if len(readings) > 1 else readings[0]
    if not merged or not merged.get('labels'):
        return {'labels': [], 'message': '品名表示を読み取れませんでした。', 'frame_analysis':analysis,'frames':len(frames)}
    merged = dict(merged)
    merged['frames'] = len(frames)
    merged['frame_analysis'] = analysis
    merged['message'] = f"{len(merged['labels'])}行（ALT表示中に{len(frames)}枚撮影・{len(readings)}枚を照合）"
    return merged
