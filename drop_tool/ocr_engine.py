"""同梱モデルで品名を読む。通信・PowerShell・GPUは使わない。

入力仕様はPaddleOCR/RapidOCRに従う。モデルの出典とハッシュは
models/manifest.json、ライセンスはlicenses/に保存する。
"""
from functools import lru_cache
import hashlib
import json
import math
import threading
import cv2
import numpy as np
from PIL import Image
from .config import ROOT


def check_model(root=ROOT):
    """モデルの取り違えや展開漏れを検出する。ダウンロードはしない。"""
    manifest = json.loads((root / 'models/manifest.json').read_text('utf-8'))
    model = root / 'models/japanese-rec.onnx'
    if not model.is_file():
        raise RuntimeError('OCRモデルがありません。modelsフォルダーを含めて展開してください。')
    if hashlib.sha256(model.read_bytes()).hexdigest() != manifest.get('sha256'):
        raise RuntimeError('OCRモデルが破損しているか、対応する版と異なります。配布ZIPから展開し直してください。')
    return model


def prepare_image(image):
    """二値化せず濃淡・色を残して3倍拡大。元の保存画像には触れない。"""
    if image.width < 1 or image.height < 1 or image.width > 2000 or image.height > 400:
        raise ValueError('OCR用の品名画像の大きさを確認してください。')
    rgb = image.convert('RGB').resize((image.width * 3, image.height * 3), Image.Resampling.LANCZOS)
    # モデルが学習したBGR順に合わせる。表示・証拠PNGはRGBのまま。
    return np.asarray(rgb)[:, :, ::-1].copy()


class JapaneseRecognizer:
    """モデルを一度読み込み、近い幅の品名を最大6件ずつ認識する。"""
    def __init__(self, model_path=None):
        import onnxruntime as ort
        model_path = model_path or check_model()
        options = ort.SessionOptions()
        # ゲームと同時に動かすためCPU全コアを占有しない。
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.enable_cpu_mem_arena = False
        options.log_severity_level = 3
        try:
            self.session = ort.InferenceSession(str(model_path), options, providers=['CPUExecutionProvider'])
            self.input_name = self.session.get_inputs()[0].name
            alphabet = self.session.get_modelmeta().custom_metadata_map['character'].splitlines()
            self.characters = [''] + alphabet + [' ']
        except Exception as exc:
            raise RuntimeError('同梱OCRを起動できません：' + str(exc)) from exc
        self.lock = threading.Lock()

    def recognize(self, images):
        """元の行順を保持する。確信度は正解保証ではなく診断用。"""
        arrays = [prepare_image(image) for image in images]
        indices = sorted(range(len(arrays)), key=lambda i: arrays[i].shape[1] / arrays[i].shape[0])
        result = [('', 0.0)] * len(images)
        with self.lock:
            for start in range(0, len(indices), 6):
                batch = indices[start:start + 6]
                width = max(320, max(int(48 * arrays[i].shape[1] / arrays[i].shape[0]) for i in batch))
                if width > 2400:
                    raise ValueError('品名画像が横に長すぎます。複数行が結合されていないか確認してください。')
                blob = np.zeros((len(batch), 3, 48, width), dtype=np.float32)
                for j, i in enumerate(batch):
                    image = arrays[i]
                    w = min(width, math.ceil(48 * image.shape[1] / image.shape[0]))
                    resized = cv2.resize(image, (w, 48)).astype(np.float32)
                    blob[j, :, :, :w] = resized.transpose(2, 0, 1) / 127.5 - 1
                try:
                    scores = self.session.run(None, {self.input_name: blob})[0]
                except Exception as exc:
                    raise RuntimeError('同梱OCRの読取に失敗しました：' + str(exc)) from exc
                if scores.shape[-1] != len(self.characters):
                    raise RuntimeError('OCRモデルの文字辞書が一致しません。')
                ids, probabilities = scores.argmax(2), scores.max(2)
                for j, i in enumerate(batch):
                    # CTCの連続重複と空白トークンだけを除く。文字の推測置換はしない。
                    keep = np.ones(len(ids[j]), dtype=bool)
                    keep[1:] = ids[j][1:] != ids[j][:-1]
                    keep &= ids[j] != 0
                    text = ''.join(self.characters[k] for k in ids[j][keep])
                    confidence = float(probabilities[j][keep].mean()) if keep.any() else 0.0
                    result[i] = (text, confidence)
        return result


@lru_cache(maxsize=1)
def engine():
    """読取時に初期化し、UI起動や設定変更でモデルを再ロードしない。"""
    return JapaneseRecognizer()


def suggestions(images):
    """画像ごとに候補名を返す。正式名への一致・未確認扱いはVision側で判断。"""
    if not images:
        return []
    from .tracker import normalize
    return [normalize(text) for text, _ in engine().recognize(images)]


def probe():
    """モデル読込と推論を実行する。実データは読み書きしない。"""
    engine().recognize([Image.new('RGB', (80, 14), 'black')])
    return 'PP-OCRv6 small / ONNX Runtime CPU'
