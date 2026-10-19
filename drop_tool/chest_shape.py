"""Weak shape evidence requires a rimmed lid and at least three nearby ALT plates."""
import cv2
import numpy as np
from PIL import Image
from .config import ROOT
from .chest_gradients import GradientClassifier

def shape(im,box,interior=True):
    x0,y0,x1,y1=box
    patch=im.crop((round(x0),round(y0),round(x1),round(y1))).convert('RGB').resize((128,160))
    a=np.asarray(patch);found=[]
    for cutoff in (16,32,48):
        dark=(a.max(2)<cutoff).astype('uint8')
        cs,_=cv2.findContours(dark,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for c in cs:
            area=cv2.contourArea(c);hull=cv2.convexHull(c);ha=cv2.contourArea(hull)
            if not(100<area<128*160*.55) or ha==0 or area/ha<.65:continue
            p=cv2.approxPolyDP(hull,.035*cv2.arcLength(hull,True),True)
            x,y,w,h=cv2.boundingRect(p)
            if len(p)!=4 or not cv2.isContourConvex(p) or not(12<=w<=110 and 20<=h<=130 and .15<=w/h<=4):continue
            if interior and (x<3 or y<3 or x+w>125 or y+h>157):continue
            if y>95:continue
            m=np.zeros((160,128),np.uint8);cv2.fillPoly(m,[p],1)
            rim=(cv2.dilate(m,np.ones((7,7),np.uint8))>0)&(m==0)
            metal=(a.max(2)-a.min(2)<50)&(a.max(2)>65)&(a.max(2)<235)
            score=float(metal[rim].mean()) if rim.any() else 0.
            if score>=.25:found.append({'cutoff':cutoff,'rim':score,'box':[x,y,x+w,y+h]})
    return found


def plate_rows(image):
    """Return ALT plate positions without OCR or loading recognition models."""
    from .vision import Vision, CENTER
    plates = Vision.boxes(None, image)
    return [(p.info['pos'][1]+round(image.width*CENTER[0]),
             p.info['pos'][0]+round(image.height*CENTER[1]),p.width,p.height)
            for p in plates]


class ChestShape:
    def __init__(self):
        self.classifier = GradientClassifier()
        with np.load(ROOT/'assets/chest-shape.npz', allow_pickle=False) as data:
            weights = data['detector']
            if weights.shape != (721,) or not np.isfinite(weights).all():
                raise ValueError('宝箱の輪郭データが不正です。')
            self.classifier.set_weights(weights)

    @staticmethod
    def near_plates(box, rows):
        x0,y0,x1,y1=box;w=x1-x0;h=y1-y0
        return sum(1 for x,y,pw,ph in rows
                   if x<x1+w*.6 and x+pw>x0-w*.6
                   and y0-h*.25<y<y1+h*1.5)>=3

    def detect(self, image, rows=None):
        if rows is None:rows=plate_rows(image)
        empty = {'found':False,'match':None,'search':'shape'}
        if len(rows)<3 or image.width<64 or image.height<80:
            return empty
        scale=min(1.,1920/image.width)
        gray=np.asarray(image.convert('L').resize((round(image.width*scale),round(image.height*scale))))
        rects,scores=self.classifier.detectMultiScale(gray,hitThreshold=.5,scale=1.12)
        for j in np.argsort(scores)[::-1]:
            x,y,w,h=rects[j];box=[float(x/scale),float(y/scale),float((x+w)/scale),float((y+h)/scale)]
            if self.near_plates(box,rows) and shape(image,box,interior=False):
                return {'found':True,'match':{'template':'shape-alt','score':float(scores[j]),
                                             'inliers':0,'box':box},'search':'shape'}
        return empty
