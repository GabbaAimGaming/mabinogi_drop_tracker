"""Local per-run loot records. Unknown observations never count as zero drops."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import re
import uuid
import unicodedata
from .config import ROOT

def normalize(text):
    return ''.join(unicodedata.normalize('NFKC', text).split())

def default_near(dungeon, difficulty):
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
        """既存JSONをハッシュ別に退避し、一時ファイルから置換する。"""
        if self.path.exists():
            raw = self.path.read_bytes()
            backup = self.folder / 'backups'
            backup.mkdir(exist_ok=True)
            target = backup / (hashlib.sha256(raw).hexdigest()[:16] + '.json')
            if not target.exists():
                target.write_bytes(raw)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), 'utf-8')
        tmp.replace(self.path)

    def new_run(self, dungeon, difficulty, near):
        """利用者の入場操作で周回を作る。報酬が同じでも別の周回として扱う。"""
        if not dungeon.strip() or not difficulty.strip() or near not in ('使用', '不使用'):
            raise ValueError('ダンジョン・難易度・ネアル使用/不使用を指定してください。')
        run = {'id': uuid.uuid4().hex, 'dungeon': dungeon.strip(), 'difficulty': difficulty.strip(), 'near': near, 'created': datetime.now().astimezone().isoformat(timespec='seconds'), 'status': 'waiting', 'rows': []}
        self.data['runs'].append(run)
        self.save()
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
        if not run['rows'] or any((row['kind'] == 'review' or not row['name'].strip() for row in run['rows'])):
            raise ValueError('未確認の行を修正してください。')
        run['status'] = 'confirmed'
        self.save()

    def stats(self, context):
        """確認済みの周回だけを分母にする。同じ品の複数行は1回にまとめる。"""
        matching = [r for r in self.data['runs'] if (r['dungeon'], r['difficulty'], r['near']) == tuple(context) and r['status'] != 'discarded']
        confirmed = [r for r in matching if r['status'] == 'confirmed']
        n = len(confirmed)
        hits = {}
        for run in confirmed:
            for name in {row['name'] for row in run['rows'] if row['kind'] == 'material'}:
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
    """ALT表示中の同じ品名一覧を連続3回確認してから記録候補にする。"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.signature = None
        self.repeats = 0
        self.ready = None

    def observe(self, result):
        """無効なフレームで安定確認をリセットする。箱の位置や角度は使わない。"""
        if not result or not result.get('labels'):
            self.reset()
            return False
        signature = tuple(sorted(((x['name'], x['kind'], x.get('fingerprint', '') if x['kind'] == 'review' else '') for x in result['labels'])))
        if signature == self.signature:
            self.repeats += 1
        else:
            self.signature = signature
            self.repeats = 1
            self.ready = None
        if self.repeats >= 3:
            self.ready = result
        return self.ready is not None

    def finish(self):
        """連続確認できた候補を渡し、次の読取へ状態を戻す。"""
        result = self.ready
        self.reset()
        return result
