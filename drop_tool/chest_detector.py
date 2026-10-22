"""試験用の宝箱検出。利用者提供の箱の輪郭内特徴を照合し、色は条件にしない。"""
import json
import time
from functools import cached_property
import cv2
import numpy as np
from PIL import Image
from .config import ROOT


class ChestDetector:
    def __init__(self):
        self.sift = cv2.SIFT_create(nfeatures=6000, contrastThreshold=.02)
        self.matcher = cv2.BFMatcher(cv2.NORM_L2)
        self.templates = []
        folder = ROOT / 'assets/chests'
        for entry in json.loads((folder/'manifest.json').read_text('utf-8'))['templates']:
            with np.load(folder/entry['file'], allow_pickle=False) as data:
                self.templates.append((entry['id'], data['points'].copy(),
                                       data['descriptors'].copy(), data['size'].copy()))

    # 補助の検出器は使う時に初めて作る（見本の読み込みを通常フレームで行わない）。
    @cached_property
    def fragments(self):
        from .chest_fragments import ChestFragments
        return ChestFragments()

    @cached_property
    def shape(self):
        from .chest_shape import ChestShape
        return ChestShape()

    @cached_property
    def parts(self):
        from .chest_parts import ChestParts
        return ChestParts()

    def detect(self, image):
        """段を順に試し、最初に見つかった結果を返す。どれも無ければ全体SIFTの結果。

        順番：全体SIFT → 品名板の近くの箱（表面マスク → 蓋の形） → 大画面の細部探索 → 部品照合。
        secondsは全段の合計時間で上書きする。
        """
        started = time.monotonic()
        result = self._detect(image)
        result['search'] = 'full'
        for stage in (self._near_plates, self._detail, self._parts):
            if result['found']:
                break
            trial = stage(image)
            if trial is not None and trial['found']:
                result = trial
        result['seconds'] = time.monotonic() - started
        return result

    def _near_plates(self, image):
        """ALT品名板の近くにある箱。品名板の行は2つの判定で共用する。"""
        from .chest_shape import plate_rows
        rows = plate_rows(image)
        trial = self.fragments.detect(image, rows)
        if trial['found']:
            return trial
        candidate = self.shape.detect(image, rows)
        if not candidate['found']:
            return candidate
        # 暗い四角形・縁・周辺文字は探索位置のヒントに限る。
        # 床やUIにも同じ形があるため、宝箱表面の特徴点が確認できるまで確定しない。
        x0, y0, x1, y1 = candidate['match']['box']
        width, height = x1 - x0, y1 - y0
        left, top = max(0, int(x0 - width * .6)), max(0, int(y0 - height * .6))
        right = min(image.width, int(x1 + width * .6))
        bottom = min(image.height, int(y1 + height * .6))
        verified = self._detect(image.crop((left, top, right, bottom)))
        if verified['found']:
            for key in ('box', 'evidence_box'):
                if key in verified['match']:
                    a, b, c, d = verified['match'][key]
                    verified['match'][key] = [a + left, b + top, c + left, d + top]
            verified['search'] = 'shape-detail'
            return verified
        return {'found': False, 'match': None, 'search': 'shape-unconfirmed',
                'candidate': candidate['match']}

    def _detail(self, image):
        """大画面の縮小で箱の特徴が消えた場合だけ、中央と蓋の候補を原寸で再探索。

        画像全体を原寸SIFTへ渡さず、通常フレームの負荷を増やさない。
        """
        if image.width <= 1600:
            return None
        regions = self._proposals(image)
        width = round(image.width * .35)
        height = round(image.height * .65)
        left = (image.width - width) // 2
        top = round(image.height * .2)
        regions.append((left, top, left + width, top + height))
        for left, top, right, bottom in regions:
            trial = self._detect(image.crop((left, top, right, bottom)))
            if trial['found']:
                for key in ('box', 'evidence_box'):
                    if key in trial['match']:
                        x0, y0, x1, y1 = trial['match'][key]
                        trial['match'][key] = [x0 + left, y0 + top, x1 + left, y1 + top]
                trial['search'] = 'detail'
                return trial
        return None

    def _parts(self, image):
        trial = self.parts.detect(image)
        return {k: v for k, v in trial.items() if k != 'parts'}

    def _proposals(self, image):
        """暗い蓋の候補を挙げるだけ。箱の成立には従来の特徴点照合が必須。"""
        scale=min(1.,1280/image.width)
        rgb=np.asarray(image.convert('RGB').resize((round(image.width*scale),round(image.height*scale)),Image.Resampling.LANCZOS))
        mask=(rgb.max(2)<16).astype(np.uint8)
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        proposals=[]
        for contour in contours:
            area=cv2.contourArea(contour)
            if not 180<area<mask.size*.025:
                continue
            x,y,w,h=cv2.boundingRect(contour)
            if not (18<=w<=220 and 18<=h<=180 and .4<=w/h<=3):
                continue
            hull=cv2.contourArea(cv2.convexHull(contour))
            if not hull or area/hull<.65:
                continue
            # 蓋の周囲を広めに含め、箱本体の細部を原寸で照合する。
            left = max(0, round((x - w*.5) / scale))
            top = max(0, round((y - h*.35) / scale))
            right = min(image.width, round((x + w*1.5) / scale))
            bottom = min(image.height, round((y + h*2) / scale))
            proposals.append((area/hull*area,(left,top,right,bottom)))
        return [box for _,box in sorted(proposals,reverse=True)[:4]]

    def _detect(self, image):
        started = time.monotonic()
        scale = min(1.0, 1280/image.width)
        resized = image.convert('RGB').resize((round(image.width*scale), round(image.height*scale)), Image.Resampling.LANCZOS)
        gray = cv2.cvtColor(np.asarray(resized), cv2.COLOR_RGB2GRAY)
        keypoints, descriptors = self.sift.detectAndCompute(gray, None)
        best = None
        if descriptors is not None:
            for name, points, reference, size in self.templates:
                pairs = self.matcher.knnMatch(reference, descriptors, k=2)
                good = [a for pair in pairs if len(pair)==2 for a,b in [pair] if a.distance < .70*b.distance]
                # 参照側の複数点が同じ画面上の一点へ一致しても、面の根拠にはならない。
                good = list({m.trainIdx: m for m in sorted(good, key=lambda m: -m.distance)}.values())
                if len(good) < 6:
                    continue
                source = np.float32([points[m.queryIdx] for m in good]).reshape(-1,1,2)
                dest = np.float32([keypoints[m.trainIdx].pt for m in good]).reshape(-1,1,2)
                matrix, mask = cv2.findHomography(source, dest, cv2.RANSAC, 3.0)
                if matrix is None or mask is None:
                    continue
                count = int(mask.sum())
                if count < 6 or count/len(good) < .6:
                    continue
                support = source.reshape(-1, 2)[mask.ravel().astype(bool)]
                if cv2.contourArea(cv2.convexHull(support)) < max(20., float(np.prod(size)) * .035):
                    continue  # 狭い一部分・ほぼ一直線だけの一致で箱全体を推定しない。
                w,h = size
                corners = np.float32([[0,0],[w,0],[w,h],[0,h]]).reshape(-1,1,2)
                polygon = cv2.perspectiveTransform(corners,matrix).reshape(-1,2)/scale
                if not np.isfinite(polygon).all() or not cv2.isContourConvex(polygon.astype('float32')):
                    continue
                x0, y0 = polygon.min(0)
                x1, y1 = polygon.max(0)
                if not (25 < x1-x0 < image.width*.6 and 25 < y1-y0 < image.height*.6):
                    continue
                if x0<0 or y0<0 or x1>image.width or y1>image.height:
                    continue
                if best is None or count > best['inliers']:
                    evidence=dest.reshape(-1,2)[mask.ravel().astype(bool)]/scale
                    ex0, ey0 = evidence.min(0)
                    ex1, ey1 = evidence.max(0)
                    # The reference may show an open lid while matching a
                    # closed chest's body. Record actual matched surfaces too;
                    # the projected whole-reference box can include extra space.
                    best = {'template':name,'inliers':count,'box':[float(x0),float(y0),float(x1),float(y1)],
                            'evidence_box':[float(ex0),float(ey0),float(ex1),float(ey1)]}
                    if count >= 12:
                        break
        return {'found':best is not None,'match':best,'seconds':time.monotonic()-started}
