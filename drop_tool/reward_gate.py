"""宝箱を見た直後のALT表示を3秒確認する。OCRの誤読は待ち時間に影響させない。"""
from dataclasses import dataclass


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
        if not alt or now > self.chest_until or self.chest_until == 0:
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
