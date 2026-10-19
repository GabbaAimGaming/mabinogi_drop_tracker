"""赤い品名だけの補助候補。元画像は変更せず、HPバーや色付きの床を排除。"""
import cv2,numpy as np
from .label_images import red_pixels,text_pixels


def candidates(region,max_height=18):
    a=np.asarray(region.convert('RGB'));raw=red_pixels(region).astype('uint8')
    joined=cv2.morphologyEx(raw,cv2.MORPH_CLOSE,np.ones((1,13),np.uint8))
    _,_,stats,_=cv2.connectedComponentsWithStats(joined)
    result=[]
    for x,y,w,h,area in stats[1:]:
        if not(7<=h<=max_height and 25<=w<=max(550,max_height*40) and x>=3 and y>=3 and x+w+3<=region.width and y+h+3<=region.height):continue
        glyph=raw[y:y+h,x:x+w]
        # 既存の白・緑品名の脇にある赤い装備や光は、赤文字の行ではない。
        crop=region.crop((x-2,y-2,x+w+2,y+h+2))
        if red_pixels(crop).sum()<=text_pixels(crop).sum()*4:continue
        # ほぼ空の横線・塗りつぶし・単一の装備エフェクトを候補にしない。
        density=float(glyph.mean())
        if not .12<density<.75:continue
        _,_,letters,_=cv2.connectedComponentsWithStats(glyph)
        if sum(1 for bx,by,bw,bh,ba in letters[1:] if bh>=h*.45 and ba>=3)<3:continue
        edge=np.concatenate((a[y-2:y,x:x+w].reshape(-1,3),a[y+h:y+h+2,x:x+w].reshape(-1,3)))
        if np.mean(edge.max(1)<70)<.72:continue
        # チャット欄は広い暗い領域の中に行が並ぶ。品名板の左右が終わり、
        # その外側の床へ戻ることを赤文字の追加経路では必須にする。
        background=float(np.percentile(np.asarray(crop).max(2),15))
        pad=max(8,h)
        sides=(a[y:y+h,max(0,x-2*pad):max(0,x-pad)],a[y:y+h,min(region.width,x+w+pad):min(region.width,x+w+2*pad)])
        if not all(side.size and np.mean(side.max(2)>background+12)>=.35 for side in sides):continue
        result.append((int(y),int(x),region.crop((x-2,y-2,x+w+2,y+h+2))))
    return result
