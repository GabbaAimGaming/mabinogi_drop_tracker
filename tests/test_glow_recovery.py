# Full gameplay samples are private and are not distributed in this repository.
from pathlib import Path as _FixturePath
import unittest as _fixture_unittest
if not (_FixturePath(__file__).resolve().parent / 'fixtures').exists() or not (_FixturePath(__file__).resolve().parents[1] / 'tools/benchmarks/video').exists():
    raise _fixture_unittest.SkipTest('非公開の提供画像を使う回帰テスト（配布前に別環境で検証済み）')

"""発光で全行消える再現例と、文字板がない画面の除外を確認する。"""
import unittest
from pathlib import Path
from PIL import Image
from drop_tool.tracker import ROOT
from drop_tool.vision import Vision
from drop_tool.alt_display import quick_check
from drop_tool.plate_recovery import recover


class GlowRecoveryTests(unittest.TestCase):
    def test_red_glow_recovers_plate_column(self):
        with Image.open(ROOT/'tests/fixtures/red-glow-plates.png') as im:
            self.assertGreaterEqual(len(recover(im)),3)
            self.assertGreaterEqual(len(Vision.boxes(None,im,cropped=True)),3)
            self.assertTrue(quick_check(im))

    def test_blank_glow_is_not_a_column(self):
        for color in ('white','red','purple',(102,102,102)):
            im=Image.new('RGB',(600,400),color)
            self.assertEqual(recover(im),[])
            self.assertFalse(quick_check(im))

    def test_nametags_without_alt_do_not_trigger_fallback(self):
        with Image.open(ROOT/'tools/benchmarks/video/video-nametags.png') as im:
            self.assertEqual(recover(im),[])
            self.assertFalse(quick_check(im))
