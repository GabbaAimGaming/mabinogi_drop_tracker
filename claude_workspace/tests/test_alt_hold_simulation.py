# Full gameplay samples are private and are not distributed in this repository.
from pathlib import Path as _FixturePath
import unittest as _fixture_unittest
if not (_FixturePath(__file__).resolve().parent / 'fixtures').exists() or not (_FixturePath(__file__).resolve().parents[1] / 'tools/benchmarks/video').exists():
    raise _fixture_unittest.SkipTest('非公開の提供画像を使う回帰テスト（配布前に別環境で検証済み）')

"""ALTを5～10秒押し続けた場合の再現（回帰画像・仮想時計）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools/benchmarks'))
import alt_hold_simulation as simulation  # noqa: E402


class AltHoldSimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = simulation.from_images()

    def test_long_holds_are_read_and_sounds_are_ordered(self):
        for hold in (5, 10):
            for mode in ('full', 'center'):
                with self.subTest(hold=hold, mode=mode):
                    outcome = simulation.simulate(self.source, hold, 1, mode)
                    self.assertIsNotNone(outcome.detected)
                    self.assertEqual(len(outcome.names), 8)
                    # 撮影完了音（ALTを離してよい）はALT中に、解析完了音より先に鳴る。
                    self.assertLess(outcome.captured_sound, hold)
                    self.assertLess(outcome.captured_sound, outcome.complete_sound)
                    self.assertLessEqual(outcome.frames, 6)

    def test_slow_pc_still_reads_before_long_hold_ends(self):
        outcome = simulation.simulate(self.source, 5, 3, 'center')
        self.assertEqual(len(outcome.names), 8)
        self.assertLess(outcome.captured_sound, 5)

    def test_no_alt_display_records_nothing(self):
        before, _, after, fps = self.source
        outcome = simulation.simulate((before, before, after, fps), 5, 1, 'center')
        self.assertIsNone(outcome.detected)


if __name__ == '__main__':
    unittest.main()
