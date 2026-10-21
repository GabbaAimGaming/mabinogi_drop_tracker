"""Small gradient-cell linear classifier. No extra runtime dependencies."""
import cv2,numpy as np

class GradientClassifier:
    def cells(self,gray):
        h,w=gray.shape;gray=gray[:h//8*8,:w//8*8].astype('float32')
        gx=cv2.Sobel(gray,cv2.CV_32F,1,0,ksize=1);gy=cv2.Sobel(gray,cv2.CV_32F,0,1,ksize=1)
        mag,angle=cv2.cartToPolar(gx,gy,angleInDegrees=True)
        bins=(angle%180/20).astype('int32')%9
        h,w=gray.shape;yy,xx=np.indices((h,w));index=((yy//8)*(w//8)+xx//8)*9+bins
        hist=np.bincount(index.ravel(),weights=mag.ravel(),minlength=(h//8)*(w//8)*9).reshape(h//8,w//8,9).astype('float32')
        norm=np.sqrt((hist*hist).sum(2,keepdims=True)+100.)
        return hist/norm
    def compute(self,gray):return self.cells(gray).reshape(-1,1)
    def set_weights(self,weights):self.weights=np.asarray(weights[:-1]).reshape(10,8,9);self.bias=float(weights[-1])
    def detectMultiScale(self,gray,hitThreshold=.5,winStride=None,padding=None,scale=1.12,finalThreshold=0):
        rects=[];values=[];factor=1.
        for _ in range(16):
            w,h=round(gray.shape[1]/factor),round(gray.shape[0]/factor)
            if w<64 or h<80:break
            if w>0 and h>0:
                a=cv2.resize(gray,(w,h),interpolation=cv2.INTER_AREA)
                cells=self.cells(a);sh=cells.shape[0]-9;sw=cells.shape[1]-7
                scores=np.full((sh,sw),self.bias,np.float32)
                for c in range(9):scores+=cv2.filter2D(cells[:,:,c],-1,self.weights[:,:,c],anchor=(0,0))[:sh,:sw]
                ys,xs=np.where(scores>hitThreshold)
                order=np.argsort(scores[ys,xs])[::-1][:60]
                for k in order:
                    x,y=xs[k],ys[k];rects.append([round(x*8*factor),round(y*8*factor),round(64*factor),round(80*factor)]);values.append(float(scores[y,x]))
            factor*=scale
        return np.asarray(rects,dtype='int32').reshape(-1,4),np.asarray(values)
