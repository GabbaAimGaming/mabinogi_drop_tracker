"""試験用の宝箱検出。利用者提供の箱の輪郭内特徴を照合し、色は条件にしない。"""
import json
import time
import cv2
import numpy as np
from PIL import Image
from .config import ROOT


class ChestDetector:
    def __init__(self):
        self.sift = cv2.SIFT_create(nfeatures=6000, contrastThreshold=.02)
        self.matcher = cv2.BFMatcher(cv2.NORM_L2)
        self.templates = []
        self.parts = None
        self.shape = None
        self.fragments = None
        folder = ROOT / 'assets/chests'
        for entry in json.loads((folder/'manifest.json').read_text('utf-8'))['templates']:
            with np.load(folder/entry['file'], allow_pickle=False) as data:
                self.templates.append((entry['id'], data['points'].copy(),
                                       data['descriptors'].copy(), data['size'].copy()))

    def detect(self, image):
        started = time.monotonic()
        result = self._detect(image)
        result['search'] = 'full'
        if not result['found']:
            from .chest_fragments import ChestFragments
            from .chest_shape import ChestShape,plate_rows
            rows=plate_rows(image)
            if self.fragments is None:self.fragments=ChestFragments()
            trial=self.fragments.detect(image,rows)
            if trial['found']:
                result=trial
            else:
                if self.shape is None:self.shape=ChestShape()
                trial=self.shape.detect(image,rows)
                if trial['found']:result=trial
        # 大画面の縮小で箱の特徴が消えた場合だけ、中央を高い密度で再探索。
        # 画像全体を原寸SIFTへ渡さず、通常フレームの負荷を増やさない。
        if not result['found'] and image.width > 1600:
            regions = self._proposals(image)
            width=round(image.width*.35);height=round(image.height*.65)
            left=(image.width-width)//2;top=round(image.height*.2)
            regions.append((left,top,left+width,top+height))
            for left,top,right,bottom in regions:
                trial=self._detect(image.crop((left,top,right,bottom)))
                if trial['found']:
                    for key in ('box','evidence_box'):
                        if key in trial['match']:
                            x0,y0,x1,y1=trial['match'][key]
                            trial['match'][key]=[x0+left,y0+top,x1+left,y1+top]
                    result=trial;result['search']='detail'
                    break
        if not result['found']:
            from .chest_parts import ChestParts
            if self.parts is None:self.parts=ChestParts()
            trial=self.parts.detect(image)
            if trial['found']:
                result={k:v for k,v in trial.items() if k!='parts'}
        result['seconds']=time.monotonic()-started
        return result

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
            left=max(0,round((x-w*.5)/scale));top=max(0,round((y-h*.35)/scale))
            right=min(image.width,round((x+w*1.5)/scale));bottom=min(image.height,round((y+h*2)/scale))
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
                w,h = size
                corners = np.float32([[0,0],[w,0],[w,h],[0,h]]).reshape(-1,1,2)
                polygon = cv2.perspectiveTransform(corners,matrix).reshape(-1,2)/scale
                if not np.isfinite(polygon).all() or not cv2.isContourConvex(polygon.astype('float32')):
                    continue
                x0,y0 = polygon.min(0); x1,y1 = polygon.max(0)
                if not (25 < x1-x0 < image.width*.6 and 25 < y1-y0 < image.height*.6):
                    continue
                if x0<0 or y0<0 or x1>image.width or y1>image.height:
                    continue
                if best is None or count > best['inliers']:
                    evidence=dest.reshape(-1,2)[mask.ravel().astype(bool)]/scale
                    ex0,ey0=evidence.min(0); ex1,ey1=evidence.max(0)
                    # The reference may show an open lid while matching a
                    # closed chest's body. Record actual matched surfaces too;
                    # the projected whole-reference box can include extra space.
                    best = {'template':name,'inliers':count,'box':[float(x0),float(y0),float(x1),float(y1)],
                            'evidence_box':[float(ex0),float(ey0),float(ex1),float(ey1)]}
                    if count >= 12:
                        break
        return {'found':best is not None,'match':best,'seconds':time.monotonic()-started}
