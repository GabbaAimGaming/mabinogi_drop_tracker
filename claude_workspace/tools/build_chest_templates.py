"""注釈済み宝箱切り抜きから参照特徴を再生成する開発用処理。アプリからは呼ばない。"""
import json
from pathlib import Path
import sys
import cv2
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]


def build(folder, output):
    output.mkdir(parents=True,exist_ok=True)
    records=json.loads((folder/'annotations.json').read_text('utf-8'))
    sift=cv2.SIFT_create(contrastThreshold=.02,nfeatures=6000)
    templates=[]
    for record in records:
        with Image.open(folder/record['file']) as source:
            image=source.convert('RGB')
        pixels=np.asarray(image)
        mask=np.zeros(pixels.shape[:2],np.uint8)
        # 床模様を参照特徴に混ぜない。箱の輪郭内だけで特徴を抽出する。
        cv2.fillPoly(mask,[np.asarray(record['polygon'],np.int32)],255)
        mask=cv2.erode(mask,np.ones((3,3),np.uint8))
        if not record.get('no_labels'):
            floats=pixels.astype(float)
            text=(pixels.min(2)>175)|((floats[:,:,1]>120)&(floats[:,:,1]>floats[:,:,0]*1.5)&(floats[:,:,1]>floats[:,:,2]*1.4))
            mask[cv2.dilate(text.astype(np.uint8),np.ones((5,5),np.uint8))>0]=0
        points,descriptors=sift.detectAndCompute(cv2.cvtColor(pixels,cv2.COLOR_RGB2GRAY),mask)
        if descriptors is None or len(points)<6:
            raise ValueError('特徴が不足しています：'+record['id'])
        filename=record['id']+'.npz'
        np.savez_compressed(output/filename,points=np.float32([p.pt for p in points]),
                            descriptors=descriptors,size=np.int32(image.size))
        templates.append({'id':record['id'],'file':filename,'features':len(points)})
    (output/'manifest.json').write_text(json.dumps({'version':1,'experimental':True,'templates':templates},
                                                  ensure_ascii=False,indent=2),'utf-8')
    print(f'{len(templates)}種類の宝箱特徴を生成しました。')


if __name__=='__main__':
    folder=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'tools/chest-examples'
    output=Path(sys.argv[2]) if len(sys.argv)>2 else ROOT/'assets/chests'
    build(folder,output)
