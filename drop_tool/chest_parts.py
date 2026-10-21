"""ローカル試作用。蓋と本体を別の平面として照合し、同時に見えた場合だけ確定。"""
import json,time
import cv2,numpy as np
from PIL import Image
from .config import ROOT


class ChestParts:
    def __init__(self):
        self.sift=cv2.SIFT_create(nfeatures=1800,contrastThreshold=.02)
        self.matcher=cv2.BFMatcher(cv2.NORM_L2)
        self.templates=[]
        folder=ROOT/'assets/chest-parts'
        for item in json.loads((folder/'manifest.json').read_text(encoding='utf-8'))['templates']:
            with np.load(folder/item['file'],allow_pickle=False) as d:
                self.templates.append((item['id'],item['part'],d['points'].copy(),d['descriptors'].copy(),d['size'].copy()))

    def regions(self,image):
        scale=min(1.,1280/image.width)
        a=np.asarray(image.convert('RGB').resize((round(image.width*scale),round(image.height*scale)),Image.Resampling.LANCZOS))
        dark=(a.max(2)<22).astype('uint8')
        contours,_=cv2.findContours(dark,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        proposals=[]
        for c in contours:
            area=cv2.contourArea(c);x,y,w,h=cv2.boundingRect(c)
            if not (180<area<dark.size*.025 and 18<=w<=220 and 18<=h<=180 and .4<=w/h<=3):continue
            hull=cv2.contourArea(cv2.convexHull(c))
            if not hull or area/hull<.65:continue
            proposals.append((area/hull*area,(max(0,round((x-w*.7)/scale)),max(0,round((y-h*.5)/scale)),min(image.width,round((x+w*1.7)/scale)),min(image.height,round((y+h*2.5)/scale)))))
        # A bright region is a search hint only, never proof of a chest or its rarity.
        high=(a.max(2)>210).astype('uint8')
        high=cv2.morphologyEx(high,cv2.MORPH_CLOSE,np.ones((7,7),np.uint8))
        contours,_=cv2.findContours(high,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            x,y,w,h=cv2.boundingRect(c)
            if not (200<cv2.contourArea(c)<dark.size*.02 and 12<w<170 and 15<h<180):continue
            if not image.height*.18<y/scale<image.height*.85:continue
            box=(max(0,round((x-w*.8)/scale)),max(0,round((y-h*.5)/scale)),min(image.width,round((x+w*1.8)/scale)),min(image.height,round((y+h*1.8)/scale)))
            if any(abs(box[0]-b[0])+abs(box[1]-b[1])<80/scale for _,b in proposals):continue
            proposals.append((cv2.contourArea(c)*.3,box))
        return [box for _,box in sorted(proposals,reverse=True)[:6]]

    def match(self,image):
        scale=min(1.,700/image.width)
        a=np.asarray(image.convert('RGB').resize((round(image.width*scale),round(image.height*scale)),Image.Resampling.LANCZOS))
        kp,desc=self.sift.detectAndCompute(cv2.cvtColor(a,cv2.COLOR_RGB2GRAY),None)
        found=[]
        if desc is None:return found
        for name,part,points,reference,size in self.templates:
            pairs=self.matcher.knnMatch(reference,desc,k=2)
            good=[m for pair in pairs if len(pair)==2 for m,n in [pair] if m.distance<.70*n.distance]
            if len(good)<6:continue
            # Repeated matches to one feature cannot establish a plane.
            unique={m.trainIdx:m for m in sorted(good,key=lambda m:-m.distance)}
            good=list(unique.values())
            if len(good)<6:continue
            src=np.float32([points[m.queryIdx] for m in good]);dst=np.float32([kp[m.trainIdx].pt for m in good])
            matrix,mask=cv2.findHomography(src,dst,cv2.RANSAC,3.)
            if matrix is None or mask is None:continue
            keep=mask.ravel().astype(bool);count=int(keep.sum())
            if count<6 or count/len(good)<.6:continue
            # Require features across a visible area, not a thin coincident line.
            support=cv2.convexHull(src[keep]);support_area=cv2.contourArea(support)
            if support_area<max(20.,float(np.prod(size))*.035):continue
            projected=cv2.perspectiveTransform(support.reshape(-1,1,2),matrix).reshape(-1,2)/scale
            if not np.isfinite(projected).all() or not cv2.isContourConvex(projected.astype('float32')):continue
            x0,y0=projected.min(0);x1,y1=projected.max(0)
            if not (18<x1-x0<image.width and 12<y1-y0<image.height):continue
            if x0<0 or y0<0 or x1>image.width or y1>image.height:continue
            found.append({'template':name,'part':part,'inliers':count,'box':[float(x0),float(y0),float(x1),float(y1)]})
        return found

    def metal_quads(self,image):
        """黒い内面と金属の縁。単独では箱の根拠にしない。"""
        a=np.asarray(image.convert('RGB'));dark=(a.max(2)<22).astype('uint8')
        contours,_=cv2.findContours(dark,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        result=[]
        for c in contours:
            area=cv2.contourArea(c);hull=cv2.convexHull(c);ha=cv2.contourArea(hull)
            if not ha or area<180 or area/ha<.65:continue
            poly=cv2.approxPolyDP(hull,.035*cv2.arcLength(hull,True),True)
            x,y,w,h=cv2.boundingRect(poly)
            if len(poly)!=4 or not cv2.isContourConvex(poly):continue
            if not (25<=w<=image.width*.8 and 25<=h<=image.height*.8 and .4<=w/h<=3):continue
            mask=np.zeros(a.shape[:2],np.uint8);cv2.fillPoly(mask,[poly],1)
            rim=(cv2.dilate(mask,np.ones((7,7),np.uint8))>0)&(mask==0)
            metal=(a.max(2)-a.min(2)<45)&(a.max(2)>65)&(a.max(2)<235)
            if not rim.any() or float(metal[rim].mean())<.35:continue
            result.append([float(x),float(y),float(x+w),float(y+h)])
        return result

    def detect(self,image):
        started=time.monotonic();observed=[]
        for left,top,right,bottom in self.regions(image):
            patch=image.crop((left,top,right,bottom))
            matches=self.match(patch)
            for box in self.metal_quads(patch):
                for part in ('lid','body'):
                    matches.append({'template':'metal-rim-'+part,'part':part,'inliers':0,'box':box.copy()})
            for m in matches:
                x0,y0,x1,y1=m['box'];m['box']=[x0+left,y0+top,x1+left,y1+top]
            observed.extend(matches)
            for lid in (m for m in matches if m['part']=='lid'):
                lx0,ly0,lx1,ly1=lid['box'];lw=lx1-lx0;lh=ly1-ly0
                for body in (m for m in matches if m['part']=='body'):
                    if not lid['inliers'] and not body['inliers']:continue
                    bx0,by0,bx1,by1=body['box'];bw=bx1-bx0
                    if not (.35<bw/lw<3 and ly0+lh*.35<by0<ly1+lh*2):continue
                    if min(lx1,bx1)-max(lx0,bx0)<min(lw,bw)*.25:continue
                    if abs((bx0+bx1)-(lx0+lx1))>max(lw,bw)*1.5:continue
                    return {'found':True,'match':{'template':lid['template']+' + '+body['template'],'inliers':lid['inliers']+body['inliers'],'box':[min(lx0,bx0),min(ly0,by0),max(lx1,bx1),max(ly1,by1)]},'seconds':time.monotonic()-started,'search':'parts','parts':matches}
        return {'found':False,'match':None,'seconds':time.monotonic()-started,'search':'parts','parts':observed}
