"""旧App.submitと新App.submit(read_worker)の出力を同じ入力で比較する。引数：リポジトリのパス"""
import json, queue, sys, tempfile
from unittest.mock import Mock, patch
repo = sys.argv[1]
sys.path[:0] = [repo, repo + '/tests']
import _headless; _headless.install()
from PIL import Image
from drop_tool.app import App
import drop_tool.app as appmod
try:
    import drop_tool.read_worker as rw
except ImportError:
    rw = None

FRAME = Image.new('RGB', (200, 100), 'gray')


def make(found=True, triggered=True, evidence=False, near=False, center=False, epoch_shift=False):
    app = App.__new__(App)
    app.busy = False; app.epoch = 3; app.hwnd = 7; app.read_attempts = 0
    app.jobs = queue.Queue(); app.scan_trace = []
    app.settings = {'scan_mode': 'center' if center else 'full'}
    app.grab = Mock(return_value=FRAME); app.ready = Mock(return_value=True)
    app.save_capture = Mock()
    app.near_detector = Mock(); app.near_detector.detect.return_value = near
    app.chest_detector = Mock(); app.chest_detector.detect.return_value = {'found': found, 'match': None}
    gate = Mock(); gate.previous = None; gate.observe.return_value = triggered
    gate.elapsed.return_value = 1.5; gate.has_chest_evidence.return_value = evidence
    app.reward_gate = gate
    app.vision = Mock(); app.vision.analyze.side_effect = lambda f, cropped=False: {'labels': [{'name': 'x', 'cropped': cropped, 'w': f.width}], 'message': 'm'}
    if epoch_shift:
        def det(f):
            app.epoch += 1
            return near
        app.near_detector.detect.side_effect = det
    return app


def norm(o):
    if isinstance(o, Image.Image): return f'<img {o.size}>'
    if isinstance(o, dict): return {k: norm(v) for k, v in sorted(o.items()) if k != 'time'}
    if isinstance(o, (list, tuple)): return [norm(v) for v in o]
    return o


def drain(app, timeout=5):
    out = []
    while True:
        try: job = app.jobs.get(timeout=timeout)
        except queue.Empty: return out
        out.append(norm(job)); timeout = 0.5


def scenario(name, mode='live', image=None, collect=None, read_raises=False, **kw):
    app = make(**kw)
    app.manual_target = 'run-m'; app.saved_read_target = 'run-s'; app.saved_read_expected = {'rows': [1]}
    frames = collect if collect is not None else [FRAME] * 4
    patches = []
    for mod in filter(None, (appmod, rw)):
        if hasattr(mod, 'alt_capture'):
            patches.append(patch.object(mod.alt_capture, 'collect', return_value=list(frames[1:])))
            reader = Mock(side_effect=RuntimeError('read boom')) if read_raises else Mock(return_value={'labels': [{'name': 'y'}], 'message': 'ok'})
            patches.append(patch.object(mod.alt_capture, 'read', reader))
        if hasattr(mod, 'quick_check'):
            patches.append(patch.object(mod, 'quick_check', return_value=True))
    for p in patches: p.start()
    try:
        app.submit(mode, image)
        jobs = drain(app)
    finally:
        for p in patches: p.stop()
    return {'jobs': jobs, 'scan_trace': norm(app.scan_trace), 'phase': app.worker_phase,
            'attempts': app.read_attempts, 'save_capture': app.save_capture.call_count,
            'grab_calls': [list(c.args) for c in app.grab.call_args_list]}


cases = {
    'trigger_full': scenario('t'),
    'trigger_center': scenario('t', center=True),
    'trigger_few_frames': scenario('t', collect=[FRAME]),
    'trigger_read_raises': scenario('t', read_raises=True),
    'wait_no_chest': scenario('w', triggered=False),
    'wait_chest': scenario('w', triggered=False, evidence=True),
    'wait_near': scenario('w', triggered=False, near=True, evidence=True),
    'epoch_changed': scenario('e', epoch_shift=True),
    'live_with_image': scenario('i', image=FRAME),
    'manual': scenario('m', mode='manual'),
    'manual_photo': scenario('p', mode='manual_photo'),
    'saved_read': scenario('s', mode='saved_read', image=FRAME),
    'missed': scenario('x', mode='missed'),
    'test': scenario('z', mode='test', image=FRAME),
}
print(json.dumps(cases, ensure_ascii=False, sort_keys=True, default=str))
