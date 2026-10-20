"""手動撮影を周回に結び付け、確認後の元画像を残し続けない。"""
import copy
import json
import re
import uuid
from pathlib import Path


def owned_capture(store, run, value):
    if not re.fullmatch(r'[a-f0-9]{32}',run['id']):return None
    if not isinstance(value, str): return None
    path = Path(value)
    if (path.parent.as_posix() != 'evidence/' + run['id']
            or not re.fullmatch(r'manual-[a-f0-9]{32}\.png', path.name)):
        return None
    full = store.folder/path
    if not full.resolve().is_relative_to(store.folder.resolve()):return None
    if full.resolve().parent != (store.folder/'evidence'/run['id']).resolve(): return None
    return full


def save_photo(store, run_id, frame):
    run = store.find(run_id)
    path = store.folder/'evidence'/run_id/('manual-'+uuid.uuid4().hex+'.png')
    if owned_capture(store,run,path.relative_to(store.folder).as_posix()) is None:
        raise ValueError('撮影画像の保存先が不正です。')
    path.parent.mkdir(parents=True, exist_ok=True)
    try:frame.save(path)
    except Exception:
        path.unlink(missing_ok=True);raise
    original = copy.deepcopy(run)
    previous = run.get('capture_image')
    run['capture_image'] = path.relative_to(store.folder).as_posix()
    if run['status'] == 'confirmed':run['status'] = 'review'
    try: store.save()
    except Exception:
        run.clear();run.update(original)
        path.unlink(missing_ok=True)
        raise
    for candidate in path.parent.glob('manual-*.png'):
        old = owned_capture(store,run,candidate.relative_to(store.folder).as_posix())
        if old and old != path:
            try: old.unlink(missing_ok=True)
            except OSError: pass
    return path


def photos(store, run_id):
    run = store.find(run_id)
    capture = owned_capture(store, run, run.get('capture_image'))
    if capture and capture.is_file(): return [capture]
    folder = store.folder/'提出用サンプル'
    for report_path in sorted(folder.glob('*/report.json'), reverse=True):
        try:
            if not report_path.resolve().is_relative_to(folder.resolve()):continue
            report = json.loads(report_path.read_text('utf-8-sig'))
            if (report.get('run') or {}).get('id') != run_id: continue
            found = [report_path.parent/r['file'] for r in report.get('images', [])
                     if re.fullmatch(r'frame-\d{2}\.png', r.get('file', ''))]
            found = [p for p in found if p.is_file() and p.resolve().is_relative_to(folder.resolve())]
            if found: return found
        except (OSError, ValueError, TypeError): continue
    return []


def replace_reading(store, run_id, result, expected):
    run = store.find(run_id)
    if {'rows':run['rows'], 'status':run['status']} != expected:
        raise ValueError('読取中に周回が変更されました。再度画像を確認してください。')
    if not result.get('labels'): raise ValueError('品名を読み取れませんでした。元の記録は保持しています。')
    previous = copy.deepcopy(run)
    files = []
    try:
        rows = []
        for label in result['labels']:
            path = store.folder/'evidence'/run_id/('reread-'+uuid.uuid4().hex+'.png')
            path.parent.mkdir(parents=True, exist_ok=True);files.append(path)
            label['image'].save(path)
            rows.append({'name':label['name'], 'raw':label.get('raw',''), 'kind':label['kind'],
                         'image':path.relative_to(store.folder).as_posix()})
        run.update(rows=rows, status='review');run.pop('evidence_pruned', None)
        store.save()
    except Exception:
        run.clear();run.update(previous)
        for p in files:
            try:p.unlink(missing_ok=True)
            except OSError:pass
        raise
    # 古い切り抜きだけ整理。学習見本や元画像には触れない。
    for row in previous['rows']:
        path = store.folder/row.get('image','')
        if (path.parent == store.folder/'evidence'/run_id
                and re.fullmatch(r'(?:\d+|reread-[a-f0-9]{32})\.png',path.name)):
            try:path.unlink(missing_ok=True)
            except OSError:pass


def cleanup_confirmed(store):
    from .retention import fully_text
    confirmed = {r['id']:r for r in store.data['runs'] if fully_text(r,store.data)}
    for run in confirmed.values():
        if not re.fullmatch(r'[a-f0-9]{32}',run['id']):continue
        folder=store.folder/'evidence'/run['id']
        if not folder.resolve().is_relative_to(store.folder.resolve()):continue
        for path in folder.glob('manual-*.png'):
            if owned_capture(store,run,path.relative_to(store.folder).as_posix()):
                try:path.unlink(missing_ok=True)
                except OSError:pass
        referenced={r.get('image') for r in run['rows']}
        for path in folder.glob('*.png'):
            if (re.fullmatch(r'(?:\d+|reread-[a-f0-9]{32})\.png',path.name)
                    and path.relative_to(store.folder).as_posix() not in referenced):
                try:path.unlink(missing_ok=True)
                except OSError:pass
    # 自動・通常手動のサンプルは確定後テキストだけ保持。明示した提出用撮影は残す。
    for path in (store.folder/'提出用サンプル').glob('*/report.json'):
        try:
            if not path.resolve().is_relative_to(store.folder.resolve()):continue
            report=json.loads(path.read_text('utf-8-sig'))
            if ((report.get('run') or {}).get('id') not in confirmed
                    or report.get('kind') not in ('auto_success','manual_success','auto_failure','manual_failure')):continue
            for image in path.parent.glob('frame-??.png'):
                if re.fullmatch(r'frame-\d{2}\.png',image.name):image.unlink(missing_ok=True)
            path.unlink()
            try:path.parent.rmdir()
            except OSError:pass
        except (OSError,ValueError,TypeError):pass


def edit_row(store, run_id, index, names, kind):
    """その周回だけ修正・分割・行削除。共通の名前対応や学習を作らない。"""
    from .item_links import name_key
    from .tracker import normalize
    if kind not in ('material','excluded','review'):raise ValueError('扱いを選んでください。')
    names=[normalize(n) for n in names]
    if len(names)>20 or any(not n or len(n)>160 for n in names):raise ValueError('1行に1品、20品以内・各160文字以内で入力してください。')
    if any(name_key(n) in store.data.get('item_links',{}) for n in names):
        raise ValueError('共通の対応付け先になっている正式名を入力してください。')
    run=store.find(run_id);original=copy.deepcopy(run)
    if run['status']=='discarded':raise ValueError('集計対象外の周回は変更できません。')
    row=run['rows'][index]
    replacements=[{'name':name,'kind':kind,'raw':row.get('raw') or row['name'],
                   **({'image':row['image']} if row.get('image') else {})} for name in names]
    run['rows'][index:index+1]=replacements;run['status']='review'
    try:store.save()
    except Exception:
        run.clear();run.update(original);raise
