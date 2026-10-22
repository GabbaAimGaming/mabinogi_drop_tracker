"""宝箱を見た直後のALT表示を3秒確認する。OCRの誤読は待ち時間に影響させない。"""
from dataclasses import dataclass


@dataclass
class ChestConfirmation:
    """別フレームの同じ場所で箱を再確認してから、8秒の記憶へ渡す。"""
    box: tuple | None = None
    previous: float | None = None
    max_gap: float = 4.0

    def observe(self, detection, now):
        match = detection.get('match') or {}
        box = match.get('box')
        if not detection.get('found') or box is None or len(box) != 4:
            self.box = self.previous = None
            return False
        old, previous = self.box, self.previous
        self.box, self.previous = tuple(box), now
        if old is None or previous is None or not 0 < now - previous <= self.max_gap:
            return False
        # 離れた床・キャラ・UIを順番に拾っても、同じ宝箱の再確認にはしない。
        x0, y0 = max(old[0], box[0]), max(old[1], box[1])
        x1, y1 = min(old[2], box[2]), min(old[3], box[3])
        intersection = max(0, x1 - x0) * max(0, y1 - y0)
        old_area = max(0, old[2] - old[0]) * max(0, old[3] - old[1])
        new_area = max(0, box[2] - box[0]) * max(0, box[3] - box[1])
        area = min(old_area, new_area)
        return (area > 0 and .25 <= old_area / new_area <= 4
                and intersection / area >= .5)


@dataclass
class RewardGate:
    seconds: float = 3.0
    chest_memory: float = 8.0
    max_gap: float = 2.5
    since: float | None = None
    chest_until: float = 0.0
    previous: float | None = None
    acquired: bool = False

    def reset(self):
        self.since = self.previous = None
        self.chest_until = 0.0
        self.acquired = False

    def has_chest_evidence(self, now):
        """期限内に始めたALT確認は、連続観測できる間だけ完了まで待つ。"""
        if self.chest_until <= 0:
            return False
        if now <= self.chest_until:
            return True
        return (self.since is not None and self.since <= self.chest_until
                and now <= self.since + self.seconds + self.max_gap)

    def observe(self, chest, alt, now, blocked=False):
        if self.acquired:
            return False
        if self.previous is not None and (now < self.previous or now-self.previous > self.max_gap):
            self.since = None
            self.chest_until = 0.0
        self.previous = now
        if chest:
            self.chest_until = now + self.chest_memory
        if blocked:
            # 確認画面の文字をALT品名と見なさない。箱の記憶は通常の8秒で失効。
            self.since = None
            return False
        # 品名やキャラで一瞬箱が隠れても、直前の箱検出を短時間だけ保持する。
        if not alt or not self.has_chest_evidence(now):
            self.since = None
            return False
        if self.since is None:
            self.since = now
        if now-self.since >= self.seconds:
            self.acquired = True
            return True
        return False

    def elapsed(self, now):
        return 0.0 if self.since is None else max(0.0, now-self.since)
