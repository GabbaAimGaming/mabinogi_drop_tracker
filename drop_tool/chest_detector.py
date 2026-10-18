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
        folder = ROOT / 'assets/chests'
        for entry in json.loads((folder/'manifest.json').read_text('utf-8'))['templates']:
            with np.load(folder/entry['file'], allow_pickle=False) as data:
                self.templates.append((entry['id'], data['points'].copy(),
                                       data['descriptors'].copy(), data['size'].copy()))

    def detect(self, image):
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
                    best = {'template':name,'inliers':count,'box':[float(x0),float(y0),float(x1),float(y1)]}
        return {'found':best is not None,'match':best,'seconds':time.monotonic()-started}
