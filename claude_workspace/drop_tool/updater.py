"""公開GitHub・Googleドライブの更新情報と配布ZIPを検証・展開する。利用者データは対象外。"""
import hashlib
import http.cookiejar
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import time
import uuid
from urllib.parse import urlsplit, parse_qs, urlencode
from urllib.request import build_opener, HTTPCookieProcessor, HTTPRedirectHandler, Request
from zipfile import ZipFile

VERSION = '1.1'
APP_ID = 'KarenDrop'
REPOSITORY = 'GabbaAimGaming/mabinogi_drop_tracker'
RELEASES_URL = 'https://github.com/' + REPOSITORY + '/releases'
DEFAULT_SOURCE = RELEASES_URL + '/latest/download/update-info.json'
RECOVERY_URL = RELEASES_URL + '/latest/download/recovery-guide.txt'
LEGACY_FEED_ID = '1dcxGWJkqxCZ9ViOkcnQUI-mWNCZd7niN'


def effective_source(url):
    # Only the shipped legacy feed migrates. Preserve custom publishers' URLs.
    if not url or not url.strip():
        return DEFAULT_SOURCE
    try:
        if parse_qs(urlsplit(drive_url(url)).query).get('id') == [LEGACY_FEED_ID]:
            return DEFAULT_SOURCE
    except ValueError:
        pass
    return url.strip()


def download_url(url):
    if not isinstance(url, str):
        raise ValueError('更新先のURLが不正です。')
    url = url.strip()
    p = urlsplit(url)
    if (p.scheme == 'https' and p.hostname == 'github.com' and not p.username
            and p.port in (None, 443) and not p.query and not p.fragment
            and re.fullmatch('/' + re.escape(REPOSITORY) +
                             r'/releases/(?:latest/download|download/v[0-9]+(?:\.[0-9]+){1,3})/[A-Za-z0-9_.-]+', p.path)):
        return url
    return drive_url(url)

MAX_DOWNLOAD = 512 * 1024 * 1024
TOP_FILES = {'KarenDrop.exe', 'item-master.json', 'requirements.txt', 'README_EXE.txt',
             '更新内容.txt', '更新方法.txt', '現在の問題点と対処方法.txt', '検証記録.txt', 'update_helper.ps1'}
TOP_DIRS = {'_internal', 'assets', 'references', 'models', 'licenses', 'dictionary-docs'}


def version_key(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,4}(?:\.\d{1,4}){1,3}', value):
        raise ValueError('バージョン番号の形式が不正です。')
    parts = tuple(int(p) for p in value.split('.'))
    return parts + (0,) * (4 - len(parts))


def drive_url(url):
    """閲覧リンクからIDを取り出す。同名ファイルの検索はしない。"""
    parts = urlsplit(url.strip())
    if parts.scheme != 'https' or parts.hostname not in ('drive.google.com', 'drive.usercontent.google.com') or parts.username or parts.port not in (None, 443):
        raise ValueError('Googleドライブのファイルの共有リンクを入力してください。')
    match = re.fullmatch(r'/file/d/([\w-]+)/[^/]*', parts.path)
    query = parse_qs(parts.query)
    file_id = match[1] if match else query.get('id', [''])[0]
    if not re.fullmatch(r'[A-Za-z0-9_-]{10,200}', file_id) or '/folders/' in parts.path:
        raise ValueError('フォルダーではなく、ファイルの共有リンクを指定してください。')
    args = {'id': file_id, 'export': 'download'}
    resource = query.get('resourcekey', [''])[0]
    if resource:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', resource):
            raise ValueError('共有リンクの形式が不正です。')
        args['resourcekey'] = resource
    return 'https://drive.usercontent.google.com/download?' + urlencode(args)


def _allowed_url(url):
    p = urlsplit(url)
    return (p.scheme == 'https' and not p.username and p.port in (None, 443) and
            (p.hostname in ('drive.google.com', 'drive.usercontent.google.com', 'release-assets.githubusercontent.com')
             or (p.hostname == 'github.com' and p.path.startswith('/' + REPOSITORY + '/releases/'))))


class DriveRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _allowed_url(newurl):
            raise ValueError('共有権限またはダウンロード先を確認してください。ログインは不要な設定にしてください。')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ConfirmForm(HTMLParser):
    def __init__(self):
        super().__init__(); self.action = ''; self.fields = {}; self.active = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'form' and a.get('id') == 'download-form':
            self.action = a.get('action', ''); self.active = True
        if tag == 'input' and self.active and a.get('name') in ('id', 'export', 'confirm', 'uuid', 'resourcekey'):
            self.fields[a['name']] = a.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'form': self.active = False


def download(url, target, limit, progress=lambda done, total: None):
    url = download_url(url)
    opener = build_opener(DriveRedirect(), HTTPCookieProcessor(http.cookiejar.CookieJar()))
    target = Path(target)
    started = time.monotonic()
    try:
        for attempt in range(3):
            with opener.open(Request(url, headers={'User-Agent': 'KarenDropUpdater/1.0', 'Cache-Control': 'no-cache'}), timeout=30) as response:
                if not _allowed_url(response.geturl()): raise ValueError('ダウンロード先が不正です。')
                content_type = response.headers.get('Content-Type', '').lower()
                if 'text/html' in content_type:
                    if urlsplit(url).hostname not in ('drive.google.com', 'drive.usercontent.google.com'):
                        raise ValueError('GitHubから更新ファイルを取得できません。公開状況を確認してください。')
                    page = response.read(1_000_001)
                    if len(page) > 1_000_000: raise ValueError('ダウンロード確認画面が大きすぎます。')
                    form = ConfirmForm(); form.feed(page.decode('utf-8', 'replace'))
                    if not _allowed_url(form.action) or not form.fields.get('confirm') or form.fields.get('id') != parse_qs(urlsplit(url).query)['id'][0]:
                        raise ValueError('ファイルを取得できません。リンクを知っている全員が閲覧・ダウンロードできる設定か、ドライブの制限がないか確認してください。')
                    url = form.action + '?' + urlencode(form.fields)
                    continue
                total = int(response.headers.get('Content-Length', '0'))
                if total < 0 or total > limit: raise ValueError('更新ファイルの容量が上限を超えています。')
                count = 0
                with target.open('wb') as out:
                    while chunk := response.read(256 * 1024):
                        count += len(chunk)
                        if count > limit or time.monotonic() - started > 600:
                            raise ValueError('更新ファイルの容量または取得時間が上限を超えました。')
                        out.write(chunk); progress(count, total)
                if total and count != total: raise ValueError('ダウンロードが途中で切れました。もう一度お試しください。')
                return
        raise ValueError('ダウンロード確認を完了できませんでした。')
    except Exception:
        target.unlink(missing_ok=True)
        raise


def validate_info(info):
    if not isinstance(info, dict) or info.get('schema_version') != 1 or info.get('app_id') != APP_ID:
        raise ValueError('KarenDropの更新情報ファイルを指定してください。ZIP自体のリンクはこの欄では使いません。')
    version_key(info.get('version'))
    package = info.get('package')
    if package is None:
        if version_key(info['version']) > version_key(VERSION):
            raise ValueError('新版のZIPがまだ更新情報に登録されていません。配布者へ確認してください。')
        return info
    if not isinstance(package, dict): raise ValueError('更新情報のZIP指定が不正です。')
    download_url(package.get('url', ''))
    if not re.fullmatch('[a-f0-9]{64}', package.get('sha256', '')) or type(package.get('size')) is not int or not 1 <= package['size'] <= MAX_DOWNLOAD:
        raise ValueError('更新情報のハッシュ値または容量が不正です。')
    if not isinstance(info.get('release_notes', ''), str) or len(info.get('release_notes', '')) > 8000:
        raise ValueError('更新内容が長すぎます。')
    return info


def check(url, work):
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    file = work / 'update-info.json'
    from urllib.error import HTTPError
    try:
        download(effective_source(url), file, 64 * 1024)
    except HTTPError as exc:
        if exc.code == 404:
            raise ValueError('更新情報がまだ公開されていないか、見つかりません。配布ページを確認してください。') from exc
        if exc.code in (403, 429):
            raise ValueError('配布先のアクセス制限により確認できません。時間をおいて再度お試しください。') from exc
        raise
    return validate_info(json.loads(file.read_text('utf-8-sig')))


def new_work(root):
    folder = Path(root) / '.updates'
    if folder.exists() and (folder.is_symlink() or folder.stat().st_file_attributes & 0x400):
        raise ValueError('更新用フォルダーがリンクになっています。通常のフォルダーで使用してください。')
    work = folder / uuid.uuid4().hex
    work.mkdir(parents=True)
    return work


def cleanup(work, root):
    """生成した一時領域のみ。リンクを辿らず既知の親を確認して整理する。"""
    work, root = Path(work), Path(root).resolve()
    if work.parent != root/'.updates' or not re.fullmatch('[a-f0-9]{32}', work.name): return
    if not work.exists(): return
    for p in [work.parent, work] + list(work.rglob('*')):
        if p.is_symlink() or p.stat().st_file_attributes & 0x400: return
    if work.resolve().parent != root/'.updates': return
    shutil.rmtree(work)


def safe_path(name):
    if not isinstance(name, str) or '\\' in name or ':' in name:
        raise ValueError('更新ZIPのファイル名が不正です。')
    p = PurePosixPath(name)
    if p.is_absolute() or str(p) != name or any(x in ('', '.', '..') or x.endswith((' ', '.')) for x in p.parts):
        raise ValueError('更新ZIPの保存先が不正です。')
    if name not in TOP_FILES and (len(p.parts) < 2 or p.parts[0] not in TOP_DIRS):
        raise ValueError('更新対象外のファイルがZIPに含まれています：' + name)
    if any(re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', x, re.I) for x in p.parts):
        raise ValueError('更新ZIPのファイル名が不正です。')
    return name


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()


def stage(package, info, work):
    """ZIP内の許可済みファイルだけ展開。data・除外設定・更新先設定には触れない。"""
    package = Path(package); work = Path(work)
    if package.stat().st_size != info['package']['size'] or digest(package) != info['package']['sha256']:
        raise ValueError('ZIPの検証に失敗しました。ファイルの取り違え・破損の可能性があります。')
    with ZipFile(package) as archive:
        files = archive.infolist()
        if len(files) > 10000 or sum(f.file_size for f in files) > 2 * 1024**3:
            raise ValueError('展開後の容量またはファイル数が上限を超えます。')
        names = [f.filename for f in files if not f.is_dir()]
        if len({n.casefold() for n in names}) != len(names): raise ValueError('ZIPに同名ファイルが重複しています。')
        if archive.getinfo('KarenDrop/release-manifest.json').file_size > 2 * 1024**2:
            raise ValueError('更新一覧が大きすぎます。')
        manifest = json.loads(archive.read('KarenDrop/release-manifest.json').decode('utf-8-sig'))
        if manifest.get('app_id') != APP_ID or manifest.get('version') != info['version'] or manifest.get('schema_version') != 1:
            raise ValueError('ZIP内のバージョンが更新情報と一致しません。')
        records = manifest.get('files', [])
        if not isinstance(records, list) or not records: raise ValueError('更新ZIPに対象ファイルがありません。')
        seen = set()
        for item in records:
            name = safe_path(item['path'])
            if name.casefold() in seen or not re.fullmatch('[a-f0-9]{64}', item['sha256']): raise ValueError('更新一覧が不正です。')
            seen.add(name.casefold())
            entry = archive.getinfo('KarenDrop/' + name)
            if (entry.external_attr >> 16) & 0o170000 == 0o120000: raise ValueError('リンク形式のファイルは更新できません。')
        if 'karendrop.exe' not in seen or 'update_helper.ps1' not in seen: raise ValueError('本体または更新処理がありません。')
        if shutil.disk_usage(work).free < sum(archive.getinfo('KarenDrop/' + x['path']).file_size for x in records) + 100 * 1024**2:
            raise ValueError('展開用の空き容量が不足しています。')
        payload = work / 'payload'; payload.mkdir()
        for item in records:
            dest = payload / item['path']; dest.parent.mkdir(parents=True, exist_ok=True)
            with archive.open('KarenDrop/' + item['path']) as source, dest.open('wb') as target:
                shutil.copyfileobj(source, target)
            if digest(dest) != item['sha256']: raise ValueError('展開後の検証に失敗しました：' + item['path'])
        # 一覧自体は保存情報として最後に反映する。
        (payload / 'release-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), 'utf-8')
        records = records + [{'path':'release-manifest.json', 'sha256':digest(payload/'release-manifest.json')}]
        return {'version':info['version'], 'files':records, 'payload':str(payload.resolve())}


def prepare(info, work, progress=lambda done, total: None):
    work = Path(work)
    package = work / 'download.zip'
    download(info['package']['url'], package, MAX_DOWNLOAD, progress)
    return stage(package, info, work)


def launch(plan, work, root):
    if not getattr(sys, 'frozen', False): raise ValueError('本体の更新はWindows配布EXEで実行してください。')
    root, work = Path(root).resolve(), Path(work).resolve()
    plan.update(target=str(root), parent_pid=os.getpid(), from_version=VERSION,
                base_exe_sha256=digest(root/'KarenDrop.exe'))
    plan_file = work / 'plan.json'
    plan_file.write_text(json.dumps(plan, ensure_ascii=False), 'utf-8-sig')
    helper = work / 'update_helper.ps1'
    shutil.copy2(root / 'update_helper.ps1', helper)
    powershell = Path(os.environ['SYSTEMROOT']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    subprocess.Popen([str(powershell), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(helper), '-PlanFile', str(plan_file)],
                     cwd=work, creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)


def make_info(package, url):
    download_url(url)
    with ZipFile(package) as archive:
        manifest = json.loads(archive.read('KarenDrop/release-manifest.json').decode('utf-8-sig'))
        for item in manifest['files']:
            if 'KarenDrop/' + item['path'] not in archive.namelist():
                raise ValueError('差分ZIPではなく、自動更新用の全体ZIPを指定してください。')
    info = {'schema_version':1, 'app_id':APP_ID, 'version':manifest['version'], 'release_notes':manifest.get('release_notes', ''),
            'package':{'url':url.strip(), 'sha256':digest(package), 'size':Path(package).stat().st_size}}
    return validate_info(info)
