"""撮影と認識のワーカー処理。App.submitが別スレッドで呼ぶ。

Tkには触れず、結果はapp.jobsへ(epoch, mode, result, error)で返す。
撮影・判定・解析はappの属性（grab、ready、vision、reward_gate等）を通すので、
テストはAppのインスタンス属性を差し替えて検証できる。

mode:
- live：宝箱と3秒のALT表示が揃ってから連写し、候補を多数決でまとめる。
- manual：1枚を解析する（必ず確認待ち）。
- manual_photo：撮影だけして周回に結び付ける。
- saved_read：周回に結び付いた画像を解析する。
- missed / test：報告用の撮影、画像の試験読取。
"""
import time

from . import alt_capture
from .alt_display import quick_check
from .near_dialog import NearDialogDetector
from .vision import CENTER


def middle(frame):
    """中央スキャンで品名を探す範囲。"""
    w, h = frame.size
    return frame.crop((round(w * CENTER[0]), round(h * CENTER[1]),
                       round(w * CENTER[2]), round(h * CENTER[3])))


def run(app, mode, image, *, epoch, hwnd, center, manual_target=None,
        saved_target=None, saved_expected=None):
    """epochは開始時点の値。停止・周回変更後の結果はpoll側で破棄される。"""
    def put(kind, result, error=None):
        app.jobs.put((epoch, kind, result, error))

    frame = None
    frames = []
    attempted = mode == 'manual'
    try:
        if mode == 'manual_photo' and not app.ready(hwnd):
            raise ValueError('ゲームを前面にして、ALTの品名を表示して撮り直してください。')
        frame = image if image is not None else app.grab(hwnd)
        if mode == 'manual_photo':
            if not app.ready(hwnd):
                raise ValueError('撮影中に画面が切り替わりました。撮り直してください。')
            put(mode, {'frame': frame, 'run_id': manual_target})
            return
        if mode == 'missed':
            put(mode, {'frame': frame})
            return
        if mode == 'manual':
            put('start', {'manual': True})
            app.save_capture(frame)
        if mode == 'live' and image is None:
            scan = _observe(app, put, frame, epoch)
            if scan is None:
                return
            attempted = True
            put('start', {'manual': False})
            _burst(app, put, frame, frames, scan, epoch=epoch, hwnd=hwnd, center=center)
            return
        app.worker_phase = '品名を解析中'
        result = app.vision.analyze(frame)
        if mode == 'saved_read':
            result.update(run_id=saved_target, expected=saved_expected)
        if mode in ('live', 'manual'):
            result.update(frame=frame, sample_frames=[frame], attempted=True)
        put(mode, result)
    except Exception as exc:
        put(mode, {'sample_frames': frames or ([frame] if frame is not None else []),
                   'attempted': attempted}, str(exc))


def _observe(app, put, frame, epoch):
    """宝箱とALT表示を1枚分観測する。取得条件が成立したら判定内容を返す。

    ALTキーの状態はゲームが他アプリへ渡さないため、画面の表示で判断する。
    箱の探索には全体画像が必要。中央設定は品名の解析範囲だけを変える。
    """
    if app.near_detector is None:
        app.near_detector = NearDialogDetector()
    near_dialog = app.near_detector.detect(frame)
    detection = app.reward_detection(frame, near_dialog, time.monotonic())
    alt = not near_dialog and quick_check(middle(frame))
    if app.epoch != epoch:
        put('scan', {})
        return None
    now = time.monotonic()
    gate = app.reward_gate
    triggered = gate.observe(detection['found'], alt, now, blocked=near_dialog)
    scan = dict(detection, alt=bool(alt), near_dialog=near_dialog, elapsed=gate.elapsed(now))
    app.scan_trace = [*app.scan_trace, dict(scan, time=now)][-30:]
    if triggered:
        return scan
    if near_dialog:
        message = 'ネアル確認画面のため待機中。閉じてからALT表示を3秒確認します。'
    elif gate.has_chest_evidence(now):
        message = '宝箱を確認。ALT表示を3秒待っています。'
    else:
        message = '宝箱を探しています。未検出の場合は手動読取を使ってください。'
    put('scan', dict(scan, message=message))
    return None


def _burst(app, put, frame, frames, scan, *, epoch, hwnd, center):
    """品名表示中に連写して多数決で読む。framesへ連写画像を入れる（失敗時の提出用）。"""
    app.worker_phase = '取得条件成立・報酬を連写中'

    def again():
        if app.epoch != epoch:
            raise ValueError('監視が停止・変更されました。')
        return app.grab(hwnd)

    frames += alt_capture.collect(
        again, lambda f: not app.near_detector.detect(f) and quick_check(middle(f)), first=frame)
    app.worker_phase = f'撮影済み（{len(frames)}枚）・品名を解析中'
    if len(frames) < 2:
        result = {'labels': [], 'message': '品名表示中の画像が2枚以上集まりませんでした。'}
    else:
        analyze = ((lambda f: app.vision.analyze(middle(f), cropped=True)) if center
                   else app.vision.analyze)
        result = alt_capture.read(analyze, frames)
    result.update(final=True, attempted=True, sample_frames=frames,
                  detection=scan, frame=frames[len(frames) // 2])
    put('live', result)
