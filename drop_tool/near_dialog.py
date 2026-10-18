"""ネアル確認画面の固定文と二つのボタンを、位置と倍率を揃えて照合する。"""
import cv2
import numpy as np
from PIL import Image
from .config import ROOT


class NearDialogDetector:
    def __init__(self):
        folder = ROOT / 'assets/near-dialog'
        self.question = self._gray(Image.open(folder / 'question.png'))
        self.buttons = self._gray(Image.open(folder / 'buttons.png'))
        self.cache = {}

    @staticmethod
    def _gray(image):
        return cv2.cvtColor(np.asarray(image.convert('RGB')), cv2.COLOR_RGB2GRAY)

    def detect(self, image):
        # 全画面を探索するが、縮小して定期監視の負担を抑える。
        factor = min(1.0, 960 / image.width)
        gray = self._gray(image)
        if factor < 1:
            gray = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
        h, w = gray.shape
        key = (image.width, image.height)
        if key not in self.cache:
            variants = []
            for scale in np.arange(.75, 2.051, .05):
                s = float(scale * factor)
                q = cv2.resize(self.question, (round(229*s), max(5, round(15*s))), interpolation=cv2.INTER_AREA)
                b = cv2.resize(self.buttons, (round(189*s), round(42*s)), interpolation=cv2.INTER_AREA)
                variants.append((s, q, b))
            self.cache = {key: variants}
        for s, question, buttons in self.cache[key]:
            qh, qw = question.shape
            bh, bw = buttons.shape
            if qh > h or qw > w:
                continue
            scores = cv2.matchTemplate(gray, question, cv2.TM_CCOEFF_NORMED)
            # 同じ文言だけが別の場所に出ても、下のボタン配置が一致しなければ除外。
            for _ in range(3):
                _, score, _, (x, y) = cv2.minMaxLoc(scores)
                if score < .70:
                    break
                bx, by = round(x + 21*s), round(y + 78*s)
                pad = max(2, round(3*s))
                x0, y0 = max(0, bx-pad), max(0, by-pad)
                area = gray[y0:min(h, by+bh+pad), x0:min(w, bx+bw+pad)]
                if area.shape[0] >= bh and area.shape[1] >= bw:
                    button_score = float(cv2.minMaxLoc(cv2.matchTemplate(area, buttons, cv2.TM_CCOEFF_NORMED))[1])
                    if button_score >= .70:
                        return True
                scores[max(0,y-qh):y+qh, max(0,x-qw):x+qw] = -1
        return False
