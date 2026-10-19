"""全体ZIPとファイル検証一覧を生成する。data・個人設定は配布しない。"""
from pathlib import Path
import json
import sys
from zipfile import ZipFile, ZIP_DEFLATED
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from drop_tool.updater import VERSION, APP_ID, TOP_FILES, TOP_DIRS, digest


def manifest(folder):
    folder=Path(folder)
    files=[]
    for p in sorted(folder.rglob('*')):
        if not p.is_file(): continue
        rel=p.relative_to(folder).as_posix()
        if rel in TOP_FILES or p.relative_to(folder).parts[0] in TOP_DIRS:
            files.append({'path':rel,'sha256':digest(p)})
    result={'schema_version':1,'app_id':APP_ID,'version':VERSION,
            'release_notes':(folder/'更新内容.txt').read_text('utf-8-sig'), 'files':files}
    (folder/'release-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    return result


def package(folder, output):
    folder=Path(folder); result=manifest(folder)
    extras=['release-manifest.json','exclusions.json','update-source.json','配布者向け更新手順.txt','更新情報-初期登録用.json']
    with ZipFile(output,'w',ZIP_DEFLATED,compresslevel=9) as z:
        for rel in [x['path'] for x in result['files']]+extras:
            if (folder/rel).is_file(): z.write(folder/rel,'KarenDrop/'+rel)


if __name__=='__main__':
    package(Path(sys.argv[1]),Path(sys.argv[2]))
