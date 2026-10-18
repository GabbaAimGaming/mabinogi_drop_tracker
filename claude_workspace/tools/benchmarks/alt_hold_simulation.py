"""ALTを押す時間とPCの速さを変えて、自動監視が報酬を読めるかを再現する。

録画したALT表示（またはbenchmarks/videoの回帰画像）を仮想時計で再生し、
v0.15のALT連写単体の順序（定期監視 → 品名板の高速判定 → 連写 → 撮影完了音 →
多数決の解析 → 解析完了音）で処理する。撮影・判定・解析の実測時間に
「遅さ」の倍率を掛け、遅いPCを模擬する。キー入力は使わない。

使い方（ソース版のルートで）:
    python tools/benchmarks/alt_hold_simulation.py                      # 回帰画像で再生
    python tools/benchmarks/alt_hold_simulation.py --video ALT録画.mp4  # 録画で再生
    python tools/benchmarks/alt_hold_simulation.py --holds 1.5 5 10 --slow 1 2 3

録画ではALT表示の区間を自動で探し、その区間を繰り返して指定の時間だけ
押し続けた状態を作る。回帰画像は静止画なので、OCRの結果が使い回されて
実際より速く出る点に注意（判定の流れの確認用）。
"""
import argparse
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from drop_tool import alt_capture  # noqa: E402
from drop_tool.alt_display import quick_check  # noqa: E402
from drop_tool.tracker import Store  # noqa: E402
from drop_tool.vision import CENTER, Vision  # noqa: E402

TICK = {'full': 0.7, 'center': 0.35}      # app.tick の間隔
CAPTURE_COST = {'full': 0.03, 'center': 0.02}  # 1回の撮影時間（実機の目安）
POLL = 0.15                                 # app.poll の間隔（音が鳴るまでの最大遅れ）
LEAD = 1.78                                 # ALTを押すまでの時間（録画と同じ）
TAIL = 3.0                                  # ALTを離した後に観察する時間


def crop(image):
    w, h = image.size
    return image.crop((round(w * CENTER[0]), round(h * CENTER[1]),
                       round(w * CENTER[2]), round(h * CENTER[3])))


class Timeline:
    """仮想時刻→画面。before / ALT区間（繰り返し）/ after の3つの列から選ぶ。"""

    def __init__(self, before, during, after, fps, hold):
        self.before, self.during, self.after = before, during, after
        self.fps, self.hold = fps, hold
        self.cache = {}

    def frame(self, t):
        if t < LEAD:
            seq, i = self.before, int(t * self.fps)
        elif t < LEAD + self.hold:
            seq, i = self.during, int((t - LEAD) * self.fps)
        else:
            seq, i = self.after, int((t - LEAD - self.hold) * self.fps)
        item = seq[i % len(seq)] if seq is self.during else seq[min(i, len(seq) - 1)]
        if isinstance(item, Path):
            if item not in self.cache:
                if len(self.cache) > 64:
                    self.cache.clear()
                with Image.open(item) as source:
                    self.cache[item] = source.convert('RGB')
            return self.cache[item]
        return item


def from_images():
    folder = ROOT / 'tools' / 'benchmarks' / 'video'
    def load(name):
        with Image.open(folder / name) as source:
            return source.convert('RGB')
    return [load('video-nametags.png')], [load('video-alt-loot.png')], [load('video-after-release.png')], 60


def from_video(path, work):
    """録画を中央範囲のPNGに展開し、ALT表示の区間を自動で探す。"""
    import cv2
    capture = cv2.VideoCapture(str(path))
    fps = capture.get(cv2.CAP_PROP_FPS) or 60
    files, active = [], []
    index = 0
    while True:
        ok, bgr = capture.read()
        if not ok:
            break
        image = crop(Image.fromarray(bgr[:, :, ::-1]))
        file = work / f'{index:05d}.png'
        image.save(file)
        files.append(file)
        active.append(_alt_visible(image))
        index += 1
    capture.release()
    if not any(active):
        raise SystemExit('録画にALTの品名表示が見つかりません。')
    first = active.index(True)
    last = len(active) - 1 - active[::-1].index(True)
    print(f'録画：{len(files)}フレーム・{fps:.0f}fps。ALT表示 {first / fps:.2f}～{(last + 1) / fps:.2f}秒')
    return files[:first], files[first:last + 1], files[last + 1:] or files[-1:], fps


def _alt_visible(region):
    """品名板の列（alt_display.select）が1行以上あるか。"""
    return bool(Vision.boxes(None, region, cropped=True))


@dataclass
class Outcome:
    detected: float = None
    captured_sound: float = None
    complete_sound: float = None
    frames: int = 0
    names: tuple = ()


def simulate(source, hold, slow, mode):
    """1回分を仮想時計で再生する。時刻はALTを押した瞬間を0とした秒。"""
    before, during, after, fps = source
    timeline = Timeline(before, during, after, fps, hold)
    vision = Vision(Store(tempfile.mkdtemp()))
    now = [0.0]

    def grab():
        image = timeline.frame(now[0])
        now[0] += CAPTURE_COST[mode] * slow
        return image

    def check(image):
        started = time.perf_counter()
        visible = quick_check(image)
        now[0] += (time.perf_counter() - started) * slow
        return visible

    def sleep(seconds):
        now[0] += seconds

    def analyze(image):
        return vision.analyze(image, cropped=True)

    result = Outcome()
    t = TICK[mode]
    while t < LEAD + hold + TAIL:
        now[0] = t
        first = grab()
        if check(first):
            result.detected = now[0] - LEAD
            frames = alt_capture.collect(grab, check, first=first, clock=lambda: now[0], sleep=sleep)
            result.frames = len(frames)
            result.captured_sound = now[0] + POLL - LEAD
            started = time.perf_counter()
            read = alt_capture.read(analyze, frames)
            result.complete_sound = now[0] + (time.perf_counter() - started) * slow + POLL - LEAD
            result.names = tuple(label['name'] for label in read['labels'])
            return result
        t = max(t + TICK[mode], now[0])
    return result


def describe(outcome, hold):
    if outcome.detected is None:
        return '検知できず（記録なし）'
    def when(t):
        return 'ALT中' if t < hold else f'離して{t - hold:.1f}秒後'
    return (f'検知 {outcome.detected:.2f}s / 撮影完了音 {outcome.captured_sound:.2f}s（{when(outcome.captured_sound)}）'
            f' / 解析完了音 {outcome.complete_sound:.2f}s（{when(outcome.complete_sound)}） / '
            f'{outcome.frames}枚撮影・{len(outcome.names)}品')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--video', type=Path, help='ALT表示の録画（mp4など）')
    parser.add_argument('--holds', type=float, nargs='+', default=[1.45, 5, 10], help='ALTを押す秒数')
    parser.add_argument('--slow', type=float, nargs='+', default=[1, 2, 3], help='PCの遅さ（倍）')
    parser.add_argument('--modes', nargs='+', default=['full', 'center'], choices=list(TICK))
    parser.add_argument('--names', action='store_true', help='読み取った品名も表示する')
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as work:
        source = from_video(args.video, Path(work)) if args.video else from_images()
        if not args.video:
            print('回帰画像（静止画）で再生します。OCR結果が使い回されるため、解析は実際より速く出ます。')
        for hold in args.holds:
            print(f'== ALTを{hold:g}秒押した場合')
            for slow in args.slow:
                for mode in args.modes:
                    outcome = simulate(source, hold, slow, mode)
                    label = '全体' if mode == 'full' else '中央'
                    print(f'  {label} x{slow:g}: {describe(outcome, hold)}')
                    if args.names and outcome.names:
                        print('     ', '、'.join(outcome.names))
    return 0


if __name__ == '__main__':
    sys.exit(main())
