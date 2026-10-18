# Full gameplay samples are private and are not distributed in this repository.
from pathlib import Path as _FixturePath
import unittest as _fixture_unittest
if not (_FixturePath(__file__).resolve().parent / 'fixtures').exists() or not (_FixturePath(__file__).resolve().parents[1] / 'tools/benchmarks/video').exists():
    raise _fixture_unittest.SkipTest('非公開の提供画像を使う回帰テスト（配布前に別環境で検証済み）')

"""同梱モデルの実推論と、配布・入力不正時の失敗経路を確認する。"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from drop_tool import ocr_engine
from drop_tool.config import ROOT
from drop_tool.item_catalog import lookup_key


class LocalOcrTests(unittest.TestCase):
    def test_empty_input_does_not_load_model(self):
        with patch.object(ocr_engine, 'engine') as load:
            self.assertEqual(ocr_engine.suggestions([]), [])
            load.assert_not_called()

    def test_missing_model_reports_how_to_repair(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'models').mkdir()
            (root / 'models/manifest.json').write_text('{}')
            with self.assertRaisesRegex(RuntimeError, 'models'):
                ocr_engine.check_model(root)

    def test_mismatched_model_is_rejected_before_loading(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'models').mkdir()
            (root / 'models/manifest.json').write_text('{"sha256":"wrong"}')
            (root / 'models/japanese-rec.onnx').write_bytes(b'wrong')
            with self.assertRaisesRegex(RuntimeError, '破損'):
                ocr_engine.check_model(root)

    def test_oversized_image_is_rejected(self):
        with self.assertRaises(ValueError):
            ocr_engine.prepare_image(Image.new('RGB', (2001, 10)))

    def test_runtime_failure_is_explained(self):
        engine = ocr_engine.engine()
        with patch.object(engine.session, 'run', side_effect=RuntimeError('runtime failed')):
            with self.assertRaisesRegex(RuntimeError, '読取に失敗'):
                engine.recognize([Image.new('RGB', (100, 14))])

    def test_original_scroll_crops_are_read_in_order_without_powershell(self):
        from drop_tool.vision import Vision
        screen = Image.new('RGB', (1920, 1080), (110, 80, 70))
        screen.paste(Image.open(ROOT / 'tests/fixtures/scroll-loot.png'), (980, 325))
        crops = Vision.boxes(None, screen)
        with patch('subprocess.run', side_effect=AssertionError('no subprocess')):
            result = ocr_engine.suggestions(crops)
        self.assertEqual(len(result), len(crops))
        self.assertEqual(lookup_key(result[1]), 'エンチャントスクロール・スケルトン')
        self.assertEqual(lookup_key(result[2]), '専用エンチャントスクロール・幻影')
        self.assertEqual(result[4], '歪曲の粉')
        self.assertEqual(result[-1], 'ビンテージキュアレスゴーグル付きキャスケット')

    def test_blank_does_not_create_loot(self):
        text = ocr_engine.suggestions([Image.new('RGB', (80, 14), 'black')])
        self.assertEqual(text, [''])

    def test_scalar_separator_normalization_is_not_general_spelling_correction(self):
        self.assertEqual(lookup_key('エンチャントスクロール－スケルトン'), 'エンチャントスクロール・スケルトン')
        self.assertEqual(lookup_key('魔カの黄金の糸'), '魔カの黄金の糸')

    def test_magic_golden_thread_is_read_without_dictionary_replacement(self):
        names = ocr_engine.suggestions([Image.open(ROOT / 'tests/fixtures/magic-thread.png')])
        self.assertEqual(names, ['魔力の黄金の糸'])
