"""既知のドルカゲージの枠を照合し、その内部の候補だけを読取から外す。"""
from functools import lru_cache
import cv2
import numpy as np
from PIL import Image
from .config import ROOT

@lru_cache(maxsize=1)
def frame_templates():
    # 中央の数字・紫ゲージは照合から外す。残量が変わっても銀色の枠で探す。
    with Image.open(ROOT / 'assets/dorcha-frame.png') as source:
        rgb = np.asarray(source.convert('RGB'))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    mask = ((rgb.max(2)-rgb.min(2)<30) & (rgb.min(2)>130)).astype('uint8')*255
    mask[:3,:] = 0
    mask[15:37,12:35] = 0
    # 白い枠だけだと明るい背景にも一致するため、隣の暗い輪郭も照合する。
    mask = cv2.dilate(mask, np.ones((3,3),'uint8'))
    return [(cv2.resize(gray,None,fx=s,fy=s),
             cv2.resize(mask,None,fx=s,fy=s,interpolation=cv2.INTER_NEAREST))
            for s in (.8,1.,1.2,1.5)]

def gauge_regions(image, candidates):
    """候補付近だけ照合する。枠の外にあるドロップ品は除外しない。"""
    if not candidates:
        return []
    gray = cv2.cvtColor(np.asarray(image.convert('RGB')), cv2.COLOR_RGB2GRAY)
    found = []
    for y,x,crop in candidates:
        # 長い品名はゲージの断片ではない。短い候補を中心に枠全体を探す。
        if crop.width > 120:
            continue
        left,top=max(0,x-85),max(0,y-85)
        patch=gray[top:min(gray.shape[0],y+85),left:min(gray.shape[1],x+crop.width+85)]
        for template, mask in frame_templates():
            h,w=template.shape
            if patch.shape[0]<h or patch.shape[1]<w:
                continue
            scores=cv2.matchTemplate(patch,template,cv2.TM_SQDIFF_NORMED,mask=mask)
            scores[~np.isfinite(scores)]=1
            score,_,(px,py),_=cv2.minMaxLoc(scores)
            if score<=.12:
                rect=(left+px,top+py,left+px+w,top+py+h)
                if rect not in found:
                    found.append(rect)
    return found

def remove_gauge_candidates(image,candidates):
    regions=gauge_regions(image,candidates)
    return [(y,x,crop) for y,x,crop in candidates
            if not any(left<=x+crop.width/2<=right and top<=y+crop.height/2<=bottom
                       for left,top,right,bottom in regions)]
