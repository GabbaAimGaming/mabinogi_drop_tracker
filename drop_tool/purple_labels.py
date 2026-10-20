"""紫文字は背景板と複数の字形が揃った行だけ追加し、アイコンやゲージを避ける。"""
import cv2
import numpy as np
from .label_images import purple_pixels, text_pixels


def candidates(region,max_height=18):
    a=np.asarray(region.convert('RGB'));raw=purple_pixels(region).astype('uint8')
    joined=cv2.morphologyEx(raw,cv2.MORPH_CLOSE,np.ones((1,13),np.uint8))
    _,_,stats,_=cv2.connectedComponentsWithStats(joined)
    result=[]
    for x,y,w,h,_ in stats[1:]:
        if not(7<=h<=max_height and 25<=w<=max(550,max_height*40)
               and x>=3 and y>=3 and x+w+3<=region.width and y+h+3<=region.height):continue
        glyph=raw[y:y+h,x:x+w]
        if not .08<float(glyph.mean())<.70:continue
        _,_,letters,_=cv2.connectedComponentsWithStats(glyph)
        letters=[c for c in letters[1:] if c[3]>=h*.45 and c[4]>=3
                 and c[2]<=h*2 and c[4]<c[2]*c[3]*.85]
        if len(letters)<3:continue
        crop=region.crop((x-2,y-2,x+w+2,y+h+2))
        if purple_pixels(crop).sum()<=text_pixels(crop).sum()*1.2:continue
        edge=np.concatenate((a[y-2:y,x:x+w].reshape(-1,3),a[y+h:y+h+2,x:x+w].reshape(-1,3)))
        if np.mean(edge.max(1)<70)<.72:continue
        background=float(np.percentile(np.asarray(crop).max(2),15));pad=max(8,h)
        sides=(a[y:y+h,max(0,x-2*pad):max(0,x-pad)],
               a[y:y+h,min(region.width,x+w+pad):min(region.width,x+w+2*pad)])
        if not all(side.size and np.mean(side.max(2)>background+12)>=.35 for side in sides):continue
        result.append((int(y),int(x),crop))
    return result
