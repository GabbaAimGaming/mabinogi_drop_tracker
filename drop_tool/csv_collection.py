"""累積CSVを名義・条件別のスナップショットとして保持する。周回を推測加算しない。"""
import copy
import csv
import hashlib
import json
from pathlib import Path
from .exporting import CSV_COLUMNS


def key(group):
    return tuple(group[name] for name in ('player', 'dungeon', 'difficulty', 'near'))


def integer(text, name):
    text = (text or '').strip()
    if not text.isascii() or not text.isdecimal():
        raise ValueError(name + 'は0以上の整数で指定してください。')
    return int(text)


def read_csv(path):
    """既存の名義付きCSVに対応。出現率欄は信用せず、件数から再計算する。"""
    groups = {}
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if (reader.fieldnames is None or len(set(reader.fieldnames)) != len(reader.fieldnames)
                or not set(CSV_COLUMNS).issubset(reader.fieldnames)):
            raise ValueError('プレイヤー名付きのドロップ記録CSVを選んでください。')
        for number, row in enumerate(reader, 2):
            try:
                if None in row:
                    raise ValueError('列数が一致しません。')
                player, dungeon, difficulty, near = [(row.get(n) or '').strip() for n in CSV_COLUMNS[:4]]
                if not all((player, dungeon, difficulty, near)):
                    raise ValueError('名義・ダンジョン・難易度・ネアルが空欄です。')
                if near not in ('使用', '不使用', '未指定'):
                    raise ValueError('ネアルの値が不正です。')
                count = integer(row['集計済み周回'], '集計済み周回')
                pending = integer(row['未確認周回'], '未確認周回')
                identity = (player, dungeon, difficulty, near)
                group = groups.setdefault(identity, dict(player=player, dungeon=dungeon,
                    difficulty=difficulty, near=near, count=count, pending=pending, items={}))
                if (count, pending) != (group['count'], group['pending']):
                    raise ValueError('同じ名義・条件で周回数が異なります。')
                item = (row.get('アイテム') or '').strip()
                if not item:
                    if (row.get('出現周回') or '').strip() or group['items']:
                        raise ValueError('品名なしの行は素材なしの条件だけに使用できます。')
                    group['_empty'] = True
                    continue
                if group.get('_empty'):
                    raise ValueError('素材なし行と品名行が混在しています。')
                hits = integer(row['出現周回'], '出現周回')
                if hits > count:
                    raise ValueError('出現周回が集計済み周回を超えています。')
                if item in group['items']:
                    raise ValueError('同じ品名の行が重複しています。')
                group['items'][item] = hits
            except ValueError as exc:
                raise ValueError(f'{Path(path).name} {number}行目：{exc}') from exc
    if not groups:
        raise ValueError('CSVに集計データがありません。')
    for group in groups.values():
        group.pop('_empty', None)
    return list(groups.values())


def load_batch(paths):
    """複数ファイルに同一名義・条件があるときは、順序で勝手に決めず拒否する。"""
    result = {}
    for path in paths:
        for group in read_csv(path):
            identity = key(group)
            if identity in result and result[identity] != group:
                raise ValueError('同じ名義・条件の異なるCSVが選ばれています。採用する1ファイルを選んでください。')
            result[identity] = group
    return list(result.values())


class CsvCollection:
    def __init__(self, folder):
        self.path = Path(folder) / 'csv_imports.json'
        self.groups = []
        if self.path.exists():
            payload = json.loads(self.path.read_text('utf-8'))
            if payload.get('version') != 1 or not isinstance(payload.get('groups'), list):
                raise ValueError('CSV集計の保存形式が不正です。元ファイルは変更していません。')
            self.groups = payload['groups']
            # 起動時に壊れた保存データを集計へ通さない。
            identities = set()
            for group in self.groups:
                identity = key(group)
                if identity in identities or not all(isinstance(v, str) and v for v in identity):
                    raise ValueError('CSV集計の名義・条件が不正です。')
                identities.add(identity)
                for field in ('count', 'pending'):
                    if type(group[field]) is not int or group[field] < 0:
                        raise ValueError('CSV集計の周回数が不正です。')
                if not isinstance(group['items'], dict) or any(
                    not name or not isinstance(name, str) or type(hits) is not int or not 0 <= hits <= group['count']
                    for name, hits in group['items'].items()):
                    raise ValueError('CSV集計の品名・件数が不正です。')

    def replace(self, incoming):
        """同じ名義・条件を丸ごと置換。保存失敗時にはメモリーも以前の状態を維持する。"""
        groups = {key(g): g for g in self.groups}
        groups.update({key(g): copy.deepcopy(g) for g in incoming})
        self._save(list(groups.values()))

    def remove_player(self, player):
        self._save([g for g in self.groups if g['player'] != player])

    def _save(self, groups):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            raw = self.path.read_bytes()
            folder = self.path.parent / 'backups'
            folder.mkdir(exist_ok=True)
            backup = folder / ('csv-' + hashlib.sha256(raw).hexdigest()[:16] + '.json')
            if not backup.exists():
                backup.write_bytes(raw)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(dict(version=1, groups=groups), ensure_ascii=False, indent=2), 'utf-8')
        temporary.replace(self.path)
        self.groups = groups

    def aggregate(self, player=None):
        """条件別に分母を1名につき1回だけ合算。個人の率を平均しない。"""
        result = {}
        for group in self.groups:
            if player is not None and group['player'] != player:
                continue
            context = key(group)[1:]
            total = result.setdefault(context, dict(count=0, pending=0, players=0, items={}))
            total['count'] += group['count']
            total['pending'] += group['pending']
            total['players'] += 1
            for item, hits in group['items'].items():
                total['items'][item] = total['items'].get(item, 0) + hits
        return result


COMBINED_LABEL = 'アルビ＋夢幻ラビ誘惑（合算）'


def filter_groups(groups, mode='all', value=None):
    """表示用に集計。元データは変更せず、率の平均ではなく周回数を合算する。"""
    if mode == 'all':
        return groups
    if mode == 'context':
        return {value: groups[value]} if value in groups else {}
    if mode == 'dungeon':
        selected = {c: g for c, g in groups.items() if c[0] == value}
        label = value + '（全難易度・ネアル条件合算）'
    elif mode == 'combined':
        selected = {c: g for c, g in groups.items()
                    if c[0] == 'アルビ' or (c[0] == '夢幻ラビ' and c[1] == '誘惑')}
        label = COMBINED_LABEL
    else:
        raise ValueError('不明なCSV表示条件です。')
    if not selected:
        return {}
    total = dict(count=0, pending=0, items={})
    for group in selected.values():
        total['count'] += group['count']
        total['pending'] += group['pending']
        for item, hits in group['items'].items():
            total['items'][item] = total['items'].get(item, 0) + hits
    return {(label,): total}
