"""周回・学習設定の保存と出現率の計算。未確認の観測をゼロドロップにしない。"""
import copy
import json
import re
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

from .config import ROOT

SHADOW_MISSIONS = ('全面戦争', '以夷制夷', 'スナイパー参戦', '影の世界のチャンピオン', '遭遇戦')

def normalize(text):
    """全半角と空白の差をなくし、OCR名・除外名・学習名を比較できる形にする。"""
    return ''.join(unicodedata.normalize('NFKC', text).split())

def default_near(dungeon, difficulty):
    if dungeon in SHADOW_MISSIONS:
        return '不使用'
    return '使用' if dungeon == 'アルビ' and difficulty == 'HD' else '未指定'

class Store:
    """周回と学習設定を既存JSONに保存する。追加のplayer_nameは旧版読込と互換。"""

    def __init__(self, folder=None):
        self.folder = Path(folder or ROOT / 'data')
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / 'records.json'
        self.data = json.loads(self.path.read_text('utf-8')) if self.path.exists() else {'version': 1, 'runs': [], 'templates': [], 'overrides': {}}
        if self.data.get('version') != 1 or not isinstance(self.data.get('runs'), list):
            raise ValueError('記録形式が不正です。上書きせず停止しました。')
        from .item_links import resolve_name
        if not isinstance(self.data.get('item_links', {}), dict):
            raise ValueError('品名の対応付けの保存形式が不正です。')
        for name in self.data.get('item_links', {}):
            resolve_name(self.data, name)

    @property
    def player_name(self):
        """旧版データには名義がないので、未入力として扱う。"""
        return self.data.get('player_name', '')

    def set_player_name(self, name):
        """データ一式の名義。空白を整え、保存失敗時はメモリーも戻す。"""
        name = name.strip()
        if len(name) > 80 or '\n' in name or '\r' in name:
            raise ValueError('プレイヤー名は改行なしの80文字以内で入力してください。')
        if name == self.player_name:
            return
        previous = self.data.get('player_name')
        self.data['player_name'] = name
        try:
            self.save()
        except Exception:
            if previous is None:
                self.data.pop('player_name', None)
            else:
                self.data['player_name'] = previous
            raise

    def save(self):
        """既存JSONをハッシュ別に退避し、一時ファイルから置換する。

        退避は新しい順に一定世代だけ残す。全保存を残すと記録量×保存回数で増え、
        500周で約0.5GBに達していた。
        """
        from .retention import backup_json
        backup_json(self.path, self.folder / 'backups')
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), 'utf-8')
        tmp.replace(self.path)

    def new_run(self, dungeon, difficulty, near):
        """利用者の入場操作で周回を作る。報酬が同じでも別の周回として扱う。"""
        if not dungeon.strip() or not difficulty.strip() or near not in ('使用', '不使用'):
            raise ValueError('ダンジョン・難易度・ネアル使用/不使用を指定してください。')
        run = {'id': uuid.uuid4().hex, 'dungeon': dungeon.strip(), 'difficulty': difficulty.strip(), 'near': near, 'created': datetime.now().astimezone().isoformat(timespec='seconds'), 'status': 'waiting', 'rows': []}
        self.data['runs'].append(run)
        try:
            self.save()
        except Exception:
            self.data['runs'].remove(run)
            raise
        return run

    def find(self, run_id):
        return next((r for r in self.data['runs'] if r['id'] == run_id))

    def delete_runs(self, run_ids):
        """記録を削除する。学習設定は残し、保存失敗時は元の周回を復元する。"""
        ids = set(run_ids)
        original = self.data['runs']
        remaining = [r for r in original if r['id'] not in ids]
        if len(remaining) == len(original):
            return 0
        self.data['runs'] = remaining
        try:
            self.save()
        except Exception:
            self.data['runs'] = original
            raise
        return len(original) - len(remaining)

    def record(self, run_id, rows, *, require_review=False):
        """未取得の周回だけを登録する。二重記録と空画面のゼロ扱いを防ぐ。"""
        run = self.find(run_id)
        if run['status'] != 'waiting':
            return False
        if not rows:
            raise ValueError('空の画面を報酬なしとして登録できません。')
        previous_rows = run['rows']
        run['rows'] = rows
        run['status'] = 'review' if require_review or any((r['kind'] == 'review' for r in rows)) else 'confirmed'
        try:
            self.save()
        except Exception:
            # 保存失敗で取得済み扱いにすると再撮影できなくなるため、未取得へ戻す。
            run['rows'] = previous_rows
            run['status'] = 'waiting'
            raise
        return True

    def confirm(self, run_id):
        """全行の集計/除外と品名が確認済みの場合だけ統計に含める。"""
        run = self.find(run_id)
        from .item_links import row_identity, name_key
        if not run['rows'] or any(kind == 'review' or not name.strip()
                                  for name, kind in (row_identity(self.data, row) for row in run['rows'])):
            raise ValueError('未確認の行を修正してください。')
        previous = copy.deepcopy(run)
        # この周回を確認した時点の扱いを記録。対応付けを後で解除しても、
        # 確認済みの行が「未確認のまま集計済み」になることを避ける。元名・元kindは残す。
        for row in run['rows']:
            if ('reviewed_kind' in row or row.get('resolved_name')
                    or name_key(row['name']) in self.data.get('item_links', {})):
                row['reviewed_kind'] = row_identity(self.data, row)[1]
        run['status'] = 'confirmed'
        try:
            self.save()
        except Exception:
            run.clear();run.update(previous)
            raise

    def stats(self, context):
        """確認済み周回を分母にし、現在の除外設定を過去の集計にも適用する。"""
        matching = [r for r in self.data['runs'] if (r['dungeon'], r['difficulty'], r['near']) == tuple(context) and r['status'] != 'discarded']
        confirmed = [r for r in matching if r['status'] == 'confirmed']
        n = len(confirmed)
        hits = {}
        from .item_links import row_identity
        from .item_catalog import ItemCatalog
        catalog = ItemCatalog(self)
        excluded = {}
        for run in confirmed:
            # 対応先へ解決してから集合にする。同じ周回に正誤両名があっても1回。
            for name in {name for name,kind in (row_identity(self.data,row) for row in run['rows']) if kind == 'material'}:
                # 元記録・周回単独の修正は保持し、集計時だけ現在の除外を優先する。
                # 「集計」への変更では過去の除外行・未確認行を自動加算しない。
                if name not in excluded:
                    excluded[name] = catalog.classify(name) == 'excluded'
                if excluded[name]:
                    continue
                hits[name] = hits.get(name, 0) + 1
        return (n, len(matching) - n, [(name, count, count / n if n else 0.0) for name, count in sorted(hits.items(), key=lambda x: (-x[1], x[0]))])

    def persist_rows(self, run_id, labels):
        """元の解像度の品名切り抜きをPNG保存する。プレビュー拡大は保存に影響しない。"""
        folder = self.folder / 'evidence' / run_id
        folder.mkdir(parents=True, exist_ok=True)
        rows = []
        for i, label in enumerate(labels):
            file = folder / f'{i:02}.png'
            label['image'].save(file)
            rows.append({'name': label['name'], 'raw': label.get('raw', ''), 'kind': label['kind'], 'image': file.relative_to(self.folder).as_posix()})
        return rows

class Rules:
    """手動学習を最優先し、JSONの名前・接頭辞・装備語尾で分類する。"""

    def __init__(self, overrides=None):
        self.rules = json.loads((ROOT / 'exclusions.json').read_text('utf-8'))
        # 旧版の個別JSONを保持した更新でも、非宝箱品の初期扱いを補う。
        # classify()冒頭の利用者による明示設定は従来どおり最優先。
        for prefix in ('フィニージェム', 'フィニージエム'):
            if prefix not in self.rules['exclude_prefix']:
                self.rules['exclude_prefix'].append(prefix)
        self.overrides = overrides or {}

    def classify(self, name):
        """自動判定できない品名はreviewにして、勝手に素材として確定しない。"""
        name = normalize(name)
        if name in self.overrides:
            return self.overrides[name]
        base = re.sub('\\((?:[\\d,]+|男性用|女性用|男女共用)\\)$', '', name)
        if base in self.rules['exclude_exact'] or any((base.startswith(p) for p in self.rules['exclude_prefix'])):
            return 'excluded'
        if base in self.rules['confirmed_materials']:
            return 'material'
        if any((base.endswith(s) for s in self.rules['equipment_suffixes'])):
            return 'excluded'
        return 'review'

class StableReading:
    """ALT表示中の品名一覧を複数フレーム読んで、1周分の報酬として確定する。

    - 同じ一覧を連続3回読めたら確定（従来どおり）。
    - ALTの品名板は半透明で、背後の動きや光で読み結果が1フレームごとに揺れる。
      そのため表示中に読んだ全フレームを保持し、ALTを離して表示が消えた時
      （2フレーム以上読めていれば）、または8フレーム読んだ時点で、行ごとの
      多数決で一覧を確定する。
    """
    NEEDED = 3
    MAX_READS = 8

    def __init__(self):
        self.reset()

    def reset(self):
        self.signature = None
        self.repeats = 0
        self.ready = None
        self.last = None
        self.readings = []

    def observe(self, result):
        """無効なフレームで安定確認をリセットする。箱の位置や角度は使わない。"""
        if not result or not result.get('labels'):
            self.reset()
            return False
        # 未確認名は同じ誤読になり得るので、切り抜きの指紋も一致させる。
        # 並び順の変動は無視するが、同名が複数行あった事実は保持する。
        signature = tuple(sorted(((x['name'], x['kind'], x.get('fingerprint', '') if x['kind'] == 'review' else '') for x in result['labels'])))
        self.last = result
        self.readings = (self.readings + [result])[-self.MAX_READS:]
        if signature == self.signature:
            self.repeats += 1
        else:
            self.signature = signature
            self.repeats = 1
            self.ready = None
        if self.repeats >= self.NEEDED:
            self.ready = result
        elif len(self.readings) >= self.MAX_READS:
            self.ready = consensus(self.readings)
        return self.ready is not None

    def release(self):
        """品名表示が消えた時、表示中に2フレーム以上読めていれば多数決の一覧を返す。

        ALT表示は押している間しか出ないため、3回一致の前に離されることがある。
        1フレームしか読めなかった一覧は誤読の恐れがあるので捨てる。
        """
        if self.ready is not None:
            result = self.ready
        elif len(self.readings) >= 2:
            result = consensus(self.readings)
        else:
            result = None
        self.reset()
        return result

    def finish(self):
        """連続確認できた候補を渡し、次の読取へ状態を戻す。"""
        result = self.ready
        self.reset()
        return result


def _same_row(a, b):
    """同じ品名板か。縦位置がほぼ同じで、横に重なる。"""
    (ya, xa, wa), (yb, xb, wb) = a, b
    return abs(ya - yb) <= 5 and xa < xb + wb and xb < xa + wa


def consensus(readings):
    """複数フレームの読取を、品名板の位置ごとの多数決で1つの一覧にまとめる。

    半数を超えるフレームに出た行だけを残す（一瞬だけ出た断片や名札を除く）。
    名前は最多の読みを採用し、同数なら辞書に登録済みの名前、次に新しい読みを優先。
    位置情報がない読取（画像確認・旧形式）は、最後の読取をそのまま使う。
    """
    if not readings:
        return None
    if any(label.get('pos') is None for r in readings for label in r['labels']):
        return readings[-1]
    rows = []
    for index, result in enumerate(readings):
        # 同名の板は小さな移動を許す。無関係な隣接行まで許容幅を広げない。
        # フレーム単位の一対一対応で、同じ品が複数落ちても票を混ぜない。
        pairs = []
        for li, label in enumerate(result['labels']):
            y, x, w = label['pos']
            for ri, row in enumerate(rows):
                ry, rx, rw = row['pos']
                same_name = (bool(normalize(label['name'])) and label['name'] != '読取不明'
                             and normalize(row['labels'][-1][1]['name']) == normalize(label['name']))
                overlap = max(0, min(x + w, rx + rw) - max(x, rx))
                moved = (same_name and abs(y - ry) <= 12
                         and overlap >= min(w, rw) * .65
                         and min(w, rw) >= max(w, rw) * .7)
                if _same_row(row['pos'], label['pos']) or moved:
                    pairs.append((not same_name, abs(y - ry), abs(x - rx), li, ri))
        assigned, used = {}, set()
        for _, _, _, li, ri in sorted(pairs):
            if li not in assigned and ri not in used:
                assigned[li] = ri
                used.add(ri)
        for li, label in enumerate(result['labels']):
            if li not in assigned:
                row = {'pos': label['pos'], 'labels': [], 'frames': set()}
                rows.append(row)
            else:
                row = rows[assigned[li]]
                row['pos'] = label['pos']
            row['labels'].append((index, label))
            row['frames'].add(index)
    total = len(readings)
    chosen = []
    for row in rows:
        if len(row['frames']) * 2 <= total:
            continue
        votes = {}
        for index, label in row['labels']:
            votes.setdefault(label['name'], []).append((index, label))
        name, entries = max(votes.items(), key=lambda item: (
            len(item[1]), bool(item[1][-1][1].get('registered')), item[1][-1][0]))
        latest = max(entries, key=lambda entry: entry[0])[1]
        chosen.append((row['pos'][0], row['pos'][1], dict(latest)))
    chosen.sort(key=lambda item: (item[0], item[1]))
    merged = dict(readings[-1])
    merged['labels'] = [label for _, _, label in chosen]
    merged['message'] = f"{len(merged['labels'])}行を{total}フレームの多数決で確定"
    return merged if merged['labels'] else None
