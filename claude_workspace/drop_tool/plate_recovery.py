"""強い発光で通常の文字領域が背景と結合した場合の補助検出。文字は生成しない。"""
import cv2
import numpy as np
from . import alt_display


def recover(region):
    a = np.asarray(region.convert('RGB')).astype(np.int16)
    r,g,b = a[:,:,0],a[:,:,1],a[:,:,2]
    colors = ((a.min(2)>175) | ((g>120)&(g>r*1.5)&(g>b*1.4))
              | ((b>100)&(r>80)&(b>g*1.3)) | ((r>140)&(r>g*1.4)&(r>b*1.2)))
    # 幅広い光柱を除き、文字の細い明部だけを取り出してから横方向に結合する。
    bright = a.max(2).astype(np.uint8)
    detail = cv2.morphologyEx(bright,cv2.MORPH_TOPHAT,np.ones((5,5),np.uint8))
    mask = (colors & (detail>35)).astype(np.uint8)
    mask = cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((1,13),np.uint8))
    _,_,stats,_ = cv2.connectedComponentsWithStats(mask)
    candidates=[]
    for x,y,w,h,_ in stats[1:]:
        if 7<=h<=18 and 25<=w<=550 and x>=2 and y>=2 and x+w+2<=region.width and y+h+2<=region.height:
            candidates.append((int(y),int(x),region.crop((x-2,y-2,x+w+2,y+h+2))))
    strong=[]
    for row in candidates:
        _,_,crop=row
        pixels=np.asarray(crop).max(2)
        # 発光の上では半透明の黒板も明るくなる。絶対的な黒さだけでは落とさず、
        # 板の平坦な背景と縦の列を併用する。床の細かい明暗を文字板にしない。
        values=pixels[2:-2,2:-2].reshape(-1)
        hist=np.bincount(values,minlength=256)
        flat=np.convolve(hist,np.ones(5,dtype=int),'same')[:121].max()/max(1,len(values))
        if flat>=.30:
            strong.append(row)
    # 追加経路では単独HUDを採用せず、少なくとも3枚がつながる列に限定する。
    groups=[]
    remaining=set(range(len(strong)))
    while remaining:
        group={remaining.pop()};pending=list(group)
        while pending:
            i=pending.pop()
            neighbors={j for j in remaining if alt_display._stacked(strong[i],strong[j])}
            remaining-=neighbors;group|=neighbors;pending.extend(neighbors)
        if len(group)>=3:groups.extend(strong[i] for i in group)
    return sorted(groups,key=lambda r:(r[0],r[1]))
