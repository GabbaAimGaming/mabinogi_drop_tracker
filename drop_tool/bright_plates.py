"""Recover translucent ALT plates over colored light from paired horizontal edges."""
import cv2
import numpy as np

def boundaries(region):
    rgb = np.asarray(region.convert('RGB'))
    a = rgb.astype(np.int16)
    r, g, b = a[:,:,0], a[:,:,1], a[:,:,2]
    color = ((a.min(2)>170) | ((g>100)&(g>r*1.4)&(g>b*1.3))
             | ((b>110)&(g>110)&(r<g*.8))
             | ((r>130)&(r>g*1.4)&(r>b*1.2))
             | ((b>110)&(r>80)&(b>g*1.3)))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    lum = gray.astype(np.float32)
    detail = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, np.ones((5,5),np.uint8))
    ink = (color & (detail>12)).astype(np.uint8)
    rows = []
    upper = (lum[:-3]+lum[1:-2])/2 - (lum[2:-1]+lum[3:])/2
    for height in range(14,25):
        count = region.height-height-4
        if count <= 0:
            continue
        # Compare two pixels outside and inside each horizontal boundary.
        top = upper[:count]
        bottom = -upper[height:height+count]
        pair = ((top>8)&(bottom>8)).astype(np.uint8)
        closed = cv2.morphologyEx(pair,cv2.MORPH_CLOSE,np.ones((1,9),np.uint8))
        _,_,stats,_ = cv2.connectedComponentsWithStats(closed)
        for x,yy,w,hh,_ in stats[1:]:
            if w<30 or w>550 or hh>8 or x<3 or x+w+3>=region.width:
                continue
            y = int(yy+np.argmax(pair[yy:yy+hh,x:x+w].sum(1))+2)
            if y+height+2>=region.height:
                continue
            strength = float(pair[y-2,x:x+w].mean())
            if strength<.70:
                continue
            patch = ink[y+2:y+height-2,x+2:x+w-2]
            density = float(patch.mean())
            if not .04<=density<=.50:
                continue
            _,_,chars,_ = cv2.connectedComponentsWithStats(patch)
            chars = [c for c in chars[1:]
                     if 2<=c[2]<=20 and 4<=c[3]<=16 and c[4]>=5]
            if len(chars)<3:
                continue
            rows.append({'box':(int(x),y,int(w),height),'edge':strength})
    # Prefer the strongest, widest boundary; suppress copies of that plate.
    kept = []
    for row in sorted(rows,key=lambda q:q['edge']*q['box'][2],reverse=True):
        x,y,w,h = row['box']
        if any(abs(y-old['box'][1])<7
               and min(x+w,old['box'][0]+old['box'][2])-max(x,old['box'][0])
               > min(w,old['box'][2])*.65 for old in kept):
            continue
        kept.append(row)
    result = []
    for row in kept:
        x,y,w,h = row['box']
        neighbors = sum(1 for other in kept
                        if h*.8<abs(other['box'][1]-y)<h*4
                        and abs(other['box'][3]-h)<5
                        and x<other['box'][0]+other['box'][2]
                        and x+w>other['box'][0])
        if neighbors>=2:
            result.append(row)
    return sorted(result,key=lambda q:(q['box'][1],q['box'][0]))


def recover(region):
    rectangles = boundaries(region)
    if len(rectangles) < 3:
        return []
    a = np.asarray(region.convert('RGB')).astype(np.int16)
    r,g,b = a[:,:,0],a[:,:,1],a[:,:,2]
    masks = [a.min(2)>170, (g>100)&(g>r*1.4)&(g>b*1.3),
             (b>110)&(g>110)&(r<g*.8), (r>130)&(r>g*1.4)&(r>b*1.2),
             (b>110)&(r>80)&(b>g*1.3)]
    gray = cv2.cvtColor(a.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    detail = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, np.ones((5,5),np.uint8))
    text = []
    for color in masks:
        mask = cv2.morphologyEx((color & (detail>15)).astype(np.uint8),
                               cv2.MORPH_CLOSE,np.ones((1,13),np.uint8))
        _,_,stats,_ = cv2.connectedComponentsWithStats(mask)
        text.extend((int(x),int(y),int(w),int(h)) for x,y,w,h,_ in stats[1:]
                    if 7<=h<=18 and 25<=w<=550)
    result=[]
    for row in rectangles:
        x,y,w,h = row['box']
        # A flare can erase most of a plate's edge. Extend only to a same-color
        # text row inside this confirmed plate, never to adjacent vertical rows.
        matches=[(tx,ty,tw,th) for tx,ty,tw,th in text
                 if 0<=ty-y<=6 and ty+th<=y+h and tx<x+w and tx+tw>x
                 and max(0,min(x+w,tx+tw)-max(x,tx))>=min(w,tw)*.5]
        if matches:
            tx,ty,tw,th=max(matches,key=lambda q:q[2])
            x0=max(0,min(x,tx-2)); x1=min(region.width,max(x+w,tx+tw+2))
        else:
            x0,x1=x,min(region.width,x+w)
        crop=region.crop((x0,y,x1,y+h))
        crop.info['recovered_plate']=True
        result.append((y+2,x0+2,crop))
    return result
