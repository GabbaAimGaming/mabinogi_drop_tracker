"""保存データの世代管理。バックアップ・ログ・証拠画像が際限なく増えるのを防ぐ。

削除してよいものだけを消す方針:
- JSONバックアップは新しい順に一定数を残す（最新は必ず残る）。
- ログは上限を超えたら1世代だけ退避して新しく書き始める。
- 証拠画像は「確定済み・全行がテキスト化済み・JSONバックアップにも同じ内容がある」
  周回だけを対象にし、新しい周回から指定世代数を残して削除する。
  学習見本（data/labels）や未確定の周回の画像は対象外。
"""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path

JSON_BACKUP_KEEP = 30
LOG_LIMIT = 1_000_000


def backup_json(path, folder, prefix='', keep=JSON_BACKUP_KEEP):
    """既存JSONをハッシュ名で退避し、古い退避を新しい順にkeep件まで減らす。"""
    path = Path(path)
    if not path.exists():
        return None
    raw = path.read_bytes()
    folder = Path(folder)
    folder.mkdir(exist_ok=True)
    target = folder / (prefix + hashlib.sha256(raw).hexdigest()[:16] + '.json')
    if target.exists():
        # 同じ内容へ戻った場合も「最新の退避」として扱い、整理で消さない。
        os.utime(target)
    else:
        target.write_bytes(raw)
    rotate(folder, prefix, keep)
    return target


def _backups(folder, prefix):
    files = [p for p in Path(folder).glob(prefix + '*.json') if p.is_file()]
    if not prefix:
        # records.jsonの退避は接頭辞なし。CSV用（csv-）などを巻き込まない。
        files = [p for p in files if '-' not in p.stem]
    return sorted(files, key=lambda p: p.stat().st_mtime_ns, reverse=True)


def rotate(folder, prefix='', keep=JSON_BACKUP_KEEP):
    """新しい順にkeep件を残す。削除できない退避は次回に再試行する。"""
    removed = 0
    for old in _backups(folder, prefix)[max(1, keep):]:
        try:
            old.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def latest_backup(folder, prefix=''):
    files = _backups(folder, prefix)
    return files[0] if files else None


def append_log(path, text, limit=LOG_LIMIT):
    """上限を超えたログは.1へ1世代だけ退避する。直前の記録を即座に失わない。"""
    path = Path(path)
    try:
        if path.exists() and path.stat().st_size > limit:
            path.replace(path.with_name(path.name + '.1'))
        with path.open('a', encoding='utf-8') as stream:
            stream.write(text)
    except OSError:
        pass


# ---- 証拠画像（data/evidence/<周回ID>/NN.png） ----

from . import settings as _settings

KEEP_RANGE = _settings.KEEP_RANGE
# [削減候補 2026-10-21] EVIDENCE_KEYS・load_settings・save_settingsは本体からの呼び出し元なし
# （読込はsettings.load、保存はApp.save_setting → settings.save）。
# 使うのはtests/test_evidence_retentionだけで、そちらはsettings.load/save経由に置き換え済み。確認後に削除
# EVIDENCE_KEYS = ('evidence_auto_delete', 'evidence_keep_runs')
#
#
# def load_settings(folder):
#     """証拠画像に関する設定だけを返す（全設定は drop_tool.settings）。"""
#     loaded = _settings.load(folder)
#     return {key: loaded[key] for key in EVIDENCE_KEYS}
#
#
# def save_settings(folder, *, evidence_auto_delete, evidence_keep_runs):
#     _settings.save(folder, evidence_auto_delete=bool(evidence_auto_delete),
#                    evidence_keep_runs=evidence_keep_runs)
#     return load_settings(folder)


def _text_rows(rows):
    return [(r.get('name', ''), r.get('kind', ''), r.get('raw', ''),
             r.get('resolved_name'), r.get('reviewed_kind')) for r in rows]


def fully_text(run, data=None):
    """全行に品名があり、集計か除外に確定している周回だけを「テキスト化済み」とする。"""
    from .item_links import row_identity
    return (run.get('status') == 'confirmed' and bool(run.get('rows'))
            and all(name.strip() and kind in ('material', 'excluded')
                    for name,kind in (row_identity(data or {}, row) for row in run['rows'])))


def has_evidence(store, run):
    return any((store.folder / row['image']).is_file()
               for row in run.get('rows', []) if row.get('image'))


def evidence_usage(store):
    """data/evidence全体の画像数とバイト数。設定画面の表示用。"""
    count = size = 0
    folder = store.folder / 'evidence'
    if folder.is_dir():
        for file in folder.rglob('*.png'):
            try:
                size += file.stat().st_size
                count += 1
            except OSError:
                pass
    return count, size


def prune_evidence(store, keep):
    """テキスト化とJSONバックアップを確認できた周回の画像だけを削除する。

    新しい確定済み周回から keep 周分は残す。未取得・確認待ち・集計対象外の
    周回、学習見本、元スクリーンショットには触れない。戻り値は削除した画像数。
    """
    if type(keep) is not int or keep < KEEP_RANGE[0]:
        raise ValueError('画像を残す世代数が不正です。')
    confirmed = [r for r in store.data['runs'] if r.get('status') == 'confirmed']
    confirmed.sort(key=lambda r: r.get('created', ''))
    targets = [r for r in confirmed[:-keep] if fully_text(r, store.data) and has_evidence(store, r)]
    if not targets:
        return 0
    # 現在のrecords.jsonを保存し、その内容がバックアップにもあることを確かめる。
    store.save()
    snapshot = latest_backup(store.folder / 'backups')
    if snapshot is None:
        return 0
    try:
        backed = {r['id']: r for r in json.loads(snapshot.read_text('utf-8')).get('runs', [])}
        on_disk = {r['id']: r for r in json.loads(store.path.read_text('utf-8')).get('runs', [])}
    except (OSError, ValueError, KeyError, TypeError):
        return 0
    removed = 0
    changed = False
    stamp = datetime.now().astimezone().isoformat(timespec='seconds')
    for run in targets:
        expected = _text_rows(run['rows'])
        if (run['id'] not in backed or _text_rows(backed[run['id']].get('rows', [])) != expected
                or run['id'] not in on_disk or _text_rows(on_disk[run['id']].get('rows', [])) != expected):
            continue
        complete = True
        for row in run['rows']:
            if not row.get('image'):
                continue
            file = store.folder / row['image']
            try:
                file.unlink()
                removed += 1
            except FileNotFoundError:
                pass
            except OSError:
                # 表示中などで消せない画像は残し、次回に再試行する。
                complete = False
        folder = store.folder / 'evidence' / run['id']
        try:
            folder.rmdir()
        except OSError:
            pass
        if complete:
            run['evidence_pruned'] = stamp
            changed = True
    if changed:
        store.save()
    return removed
