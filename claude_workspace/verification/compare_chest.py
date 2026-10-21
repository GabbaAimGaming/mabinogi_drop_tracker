"""ChestDetector.detectの旧新比較（リファクタ段階3）。引数：リポジトリのパス、出力json

各段（全体SIFT・表面マスク・蓋の形・細部探索・部品照合）を「見つかる/見つからない」に差し替え、
全組み合わせで、採用される結果・呼ばれた段・検出器の生成回数を記録する。

画像を流す比較は下にコメントアウトで残している。合成画像では全段が未検出になり、
最後の「どれも無い」分岐しか通らないため、段の順序や結果の選び方の違いを検出できない
（理由の詳細はCLAUDE.mdの§7「宝箱検知」）。
"""
import itertools, json, sys
from unittest.mock import patch
repo, out = sys.argv[1], sys.argv[2]
sys.path[:0] = [repo, repo + '/tests']
import _headless; _headless.install()
from PIL import Image
import drop_tool.chest_detector as cd
import drop_tool.chest_fragments as cf
import drop_tool.chest_shape as cs
import drop_tool.chest_parts as cp


def run(full, frag, shape, wide, proposals, detail_hit, evidence, parts):
    log = []
    size = (1920 if wide else 1280, 720)
    regions = [(100, 100, 300, 260), (900, 400, 1100, 600)][:proposals]

    def fake_detect(self, image):
        if image.size == size:
            log.append('sift-full')
            return {'found': full, 'match': {'box': [1, 2, 3, 4]} if full else None, 'seconds': 9}
        log.append(f'sift-crop{image.size}')
        index = len([x for x in log if x.startswith('sift-crop')]) - 1
        if index == detail_hit:
            match = {'template': 't', 'box': [10, 20, 30, 40]}
            if evidence:
                match['evidence_box'] = [11, 21, 31, 41]
            return {'found': True, 'match': match, 'seconds': 9}
        return {'found': False, 'match': None, 'seconds': 9}

    def stage(name, found, extra=None):
        class Stage:
            created = 0

            def __init__(self):
                Stage.created += 1
                log.append(f'new-{name}')

            def detect(self, image, rows=None):
                log.append(f'{name}{"" if rows is None else rows}')
                result = {'found': found, 'match': {'by': name} if found else None, 'seconds': 9}
                result.update(extra or {})
                return result
        return Stage

    def rows(image):
        log.append('plate_rows')
        return ['R']

    lazy_attrs = type(cd.ChestDetector.__dict__.get('parts')).__name__ != 'cached_property'

    def init(self):  # SIFTや見本の読み込みを省く（段の制御だけを見る）。旧版は属性をNoneで初期化していた
        if lazy_attrs:
            self.parts = self.shape = self.fragments = None

    results = []
    with patch.object(cd.ChestDetector, '_detect', fake_detect), \
            patch.object(cd.ChestDetector, '_proposals', lambda self, image: list(regions)), \
            patch.object(cd.ChestDetector, '__init__', init), \
            patch.object(cf, 'ChestFragments', stage('fragments', frag)), \
            patch.object(cs, 'ChestShape', stage('shape', shape)), \
            patch.object(cs, 'plate_rows', rows), \
            patch.object(cp, 'ChestParts', stage('parts', parts, {'parts': ['lid', 'body']})):
        detector = cd.ChestDetector()
        for _ in range(2):  # 2回目で検出器を作り直さないことも確認する
            result = detector.detect(Image.new('RGB', size))
            result.pop('seconds')
            results.append(result)
    return {'results': results, 'log': log}


cases = {}
for combo in itertools.product([False, True], [False, True], [False, True], [False, True],
                               [0, 2], [None, 0, 1, 2], [False, True], [False, True]):
    full, frag, shape, wide, proposals, detail_hit, evidence, parts = combo
    if detail_hit is not None and detail_hit > proposals:
        continue
    cases[repr(combo)] = run(*combo)
json.dump(cases, open(out, 'w'), sort_keys=True, default=str)
print(len(cases), 'cases')

# ---- 画像を流す比較（意味が薄いためコメントアウト。CLAUDE.md §7「宝箱検知」） ----
# from drop_tool.chest_detector import ChestDetector
# import compare_vision  # 段階2の合成画像（赤・紫の品名板、乱数の板・ゲージ・発光）
# detector = ChestDetector()
# found = {name: detector.detect(im)['found'] for name, im in compare_vision.images.items()}
# json.dump(found, open(out + '.images.json', 'w'), sort_keys=True)
