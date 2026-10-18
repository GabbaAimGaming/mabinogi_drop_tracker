# Full gameplay samples are private and are not distributed in this repository.
from pathlib import Path as _FixturePath
import unittest as _fixture_unittest
if not (_FixturePath(__file__).resolve().parent / 'fixtures').exists() or not (_FixturePath(__file__).resolve().parents[1] / 'tools/benchmarks/video').exists():
    raise _fixture_unittest.SkipTest('非公開の提供画像を使う回帰テスト（配布前に別環境で検証済み）')

"""銀色の飾りを文字として拾った報告の回帰テスト。"""
import unittest
from PIL import Image
from drop_tool.config import ROOT
from drop_tool.hud_filter import remove_gauge_candidates
from drop_tool.vision import Vision

class HudTests(unittest.TestCase):
    def test_gauge_frame_is_rejected_at_different_positions(self):
        with Image.open(ROOT/'tests/fixtures/dorcha-gauge.png') as source:
            gauge=source.convert('RGB')
        for x,y in ((800,400),(650,500),(900,300)):
            with self.subTest(position=(x,y)):
                screen=Image.new('RGB',(1920,1080),(110,80,70))
                screen.paste(gauge,(x,y))
                candidate=(y+45,x+12,screen.crop((x+12,y+43,x+55,y+59)))
                self.assertEqual(remove_gauge_candidates(screen,[candidate]),[])
    def test_nearby_short_item_is_not_removed_with_gauge(self):
        screen=Image.new('RGB',(1920,1080),(110,80,70))
        with Image.open(ROOT/'tests/fixtures/dorcha-gauge.png') as source:
            screen.paste(source,(800,400))
        with Image.open(ROOT/'references/labels/00.png') as source:
            item=source.convert('RGB')
        screen.paste(item,(790,480))
        item_candidate=(482,792,item)
        candidates=[(445,812,screen.crop((812,443,855,459))),item_candidate]
        result=remove_gauge_candidates(screen,candidates)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0][:2],item_candidate[:2])
    def test_full_detection_keeps_loot_with_gauge_nearby(self):
        screen=Image.new('RGB',(1920,1080),(110,80,70))
        with Image.open(ROOT/'tests/fixtures/overlapping-loot.png') as source:
            screen.paste(source,(800,380))
        with Image.open(ROOT/'tests/fixtures/dorcha-gauge.png') as source:
            screen.paste(source,(730,450))
        self.assertEqual(len(Vision.boxes(None,screen)),11)
