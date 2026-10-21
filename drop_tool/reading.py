"""ALT表示中に読んだ複数フレームを、1周分の品名一覧に確定する。"""
from .names import normalize


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
