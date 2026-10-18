"""発光背景で落ちる品名行の補助検出。画素は変更せず切り抜き座標だけ返す。"""
import cv2
import numpy as np


def recover_rows(image):
    """発光で欠けた行の(x, y, 幅, 高さ)を画像内座標で返す。

    7～18pxの文字高を対象とする現行閾値。近傍行のある領域だけを補い、
    単独の画面表示まで回収しない。DPIの自動補正は行っていない。
    """
    a = np.asarray(image.convert('RGB')).astype(float)
    white = a.min(2) > 175
    green = (a[:,:,1] > 120) & (a[:,:,1] > a[:,:,0]*1.5) & (a[:,:,1] > a[:,:,2]*1.4)
    # 水色の装備名も対象。純青のキャラクター名はこの条件に含めない。
    cyan = (a[:,:,1] > 140) & (a[:,:,2] > 140) & (a[:,:,0] < a[:,:,1]*.75)
    raw = white | green | cyan
    dark = cv2.blur((a.max(2) < 90).astype('float32'), (5,5))
    seeds = (raw & (dark > .25)).astype('uint8')
    joined = cv2.morphologyEx(seeds, cv2.MORPH_CLOSE, np.ones((1,13),'uint8'))
    _,_,stats,_ = cv2.connectedComponentsWithStats(joined)
    rows = []
    for x,y,w,h,area in sorted(stats[1:], key=lambda r:(r[1],r[0])):
        if not (7 <= h <= 18 and 25 <= w <= 550):
            continue
        # 同じ高さで途切れた文字列だけ結合。縦に重なる別行は結合しない。
        match = next((r for r in rows if abs(r[1]-y)<=1 and abs(r[3]-h)<=1 and 0<=x-r[0]-r[2]<=28),None)
        if match is not None:
            match[2] = x+w-match[0]
        else:
            rows.append([int(x),int(y),int(w),int(h)])
    result=[]
    for x,y,w,h in rows:
        # 孤立したHUD断片を回収しない。近くに別の品名行がある集合だけ補完する。
        neighbors = sum(1 for bx,by,bw,bh in rows
                        if 4 < abs(by-y) <= 65 and bx < x+w and bx+bw > x)
        if neighbors < 2:
            continue
        # 局所暗部で欠けた末尾を元の色マスクから補う。拡張は最大32px。
        band=raw[y:y+h].astype('uint8')
        band=cv2.morphologyEx(band,cv2.MORPH_CLOSE,np.ones((1,13),'uint8'))
        _,_,parts,_=cv2.connectedComponentsWithStats(band)
        for bx,by,bw,bh,_ in parts[1:]:
            if bx < x+w and bx+bw > x and bh >= h-2:
                end=min(x+w+32,int(bx+bw))
                w=max(w,end-x)
        result.append((x,y,w,h))
    return result


def merge_fragments(region, candidates):
    """同じ品名板の断片を再結合。明るい背景の切れ目は別アイテムとして残す。

    candidatesのx/yは文字開始、cropはその2px外側からの切り抜き。
    OCRした名前には依存せず、元画面の高さと間の背景だけを調べる。
    """
    a = np.asarray(region.convert('RGB'))
    merged = []
    for y,x,crop in sorted(candidates):
        left,top=max(0,x-2),max(0,y-2)
        right,bottom=left+crop.width,top+crop.height
        partner=None
        for row in reversed(merged):
            ry,rx,rl,rt,rr,rb=row
            gap=left-rr
            if abs(ry-y)>2 or abs((rb-rt)-crop.height)>2 or not 0<=gap<=max(16,crop.height*2):
                continue
            # 間の70%以上が暗い場合だけ同じ背景板とみなす。
            # 短い品名が横に並んだ場合に、距離だけで結合するのを避ける。
            band=a[max(rt,top):min(rb,bottom),rr:left]
            if band.size and np.mean(band.max(2)<90)<.70:
                continue
            partner=row
            break
        if partner is None:
            merged.append([y,x,left,top,right,bottom])
        else:
            partner[2]=min(partner[2],left)
            partner[3]=min(partner[3],top)
            partner[4]=max(partner[4],right)
            partner[5]=max(partner[5],bottom)
    return [(y,x,region.crop((left,top,right,bottom)))
            for y,x,left,top,right,bottom in merged]
