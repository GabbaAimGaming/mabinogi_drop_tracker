"""Masked chest surfaces. Requires nearby ALT plates; never matches label text."""
import json
import cv2
import numpy as np
from PIL import Image
from .config import ROOT
from .chest_shape import plate_rows,ChestShape


class ChestFragments:
    threshold=.90

    def __init__(self):
        self.templates=[]
        folder=ROOT/'assets/chest-fragments'
        for entry in json.loads((folder/'manifest.json').read_text(encoding='utf-8'))['templates']:
            with np.load(folder/entry['file'],allow_pickle=False) as data:
                gray=data['gray'].astype('float32');mask=data['mask'].astype('float32');box=data['box'].copy()
            if (gray.ndim!=2 or gray.shape!=mask.shape or box.shape!=(4,)
                    or mask.sum()<40 or not np.isfinite(gray).all()
                    or not np.isfinite(box).all() or not np.isin(mask,(0,1)).all()):
                raise ValueError('宝箱の部分見本が不正です。')
            for factor in (1.,.9,1.1):
                size=(round(gray.shape[1]*factor),round(gray.shape[0]*factor))
                target=cv2.resize(gray,size);weights=cv2.resize(mask,size,interpolation=cv2.INTER_NEAREST)
                count=float(weights.sum())
                if count<40:continue
                mean=float((target*weights).sum()/count);zero=(target-mean)*weights
                energy=float((zero*zero).sum())
                if energy<100:continue
                self.templates.append((entry['id'],zero,weights,count,energy,box*factor))

    def detect(self,image,rows=None):
        empty={'found':False,'match':None,'search':'fragments'}
        if rows is None:rows=plate_rows(image)
        if len(rows)<3:return empty
        scale=min(1.,1920/image.width)
        a=np.asarray(image.convert('L').resize((round(image.width*scale),round(image.height*scale)),Image.Resampling.LANCZOS)).astype('float32')
        x0=max(0,round((min(x for x,y,w,h in rows)-image.width*.03)*scale))
        x1=min(a.shape[1],round((max(x+w for x,y,w,h in rows)+image.width*.03)*scale))
        y0=max(0,round((min(y for x,y,w,h in rows)-image.height*.18)*scale))
        y1=min(a.shape[0],round((max(y+h for x,y,w,h in rows)+image.height*.06)*scale))
        a=a[y0:y1,x0:x1]
        if not a.size:return empty
        square=a*a;best=None
        for name,zero,mask,count,energy,box in self.templates:
            if zero.shape[0]>a.shape[0] or zero.shape[1]>a.shape[1]:continue
            cross=cv2.matchTemplate(a,zero,cv2.TM_CCORR)
            total=cv2.matchTemplate(a,mask,cv2.TM_CCORR)
            variance=np.maximum(0,cv2.matchTemplate(square,mask,cv2.TM_CCORR)-total*total/count)
            scores=cross/np.sqrt(np.maximum(1.,energy*variance))
            scores[(variance<count*40)|~np.isfinite(scores)]=0
            _,score,_,(x,y)=cv2.minMaxLoc(scores)
            if score<self.threshold:continue
            candidate=[(x+x0+float(box[0]))/scale,(y+y0+float(box[1]))/scale,
                       (x+x0+float(box[2]))/scale,(y+y0+float(box[3]))/scale]
            left,top,right,bottom=candidate
            if not (0<=left<right<=image.width and 0<=top<bottom<=image.height):continue
            if not ChestShape.near_plates(candidate,rows):continue
            if best is None or score>best['score']:
                best={'template':name,'score':float(score),'inliers':0,'box':candidate}
        return dict(empty,found=best is not None,match=best)
