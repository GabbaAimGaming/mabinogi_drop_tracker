# OCR比較と採用理由（2026-10-14）

採用：PP-OCRv6 small（RapidOCR配布のONNX形式）、ONNX Runtime CPU。
同じ素材で試した候補の中で、認識の一致数と速度・配布容量のバランスが良かったため採用。
全OCRに対する普遍的な最適性や、別PC・別画面での正解率を保証するものではありません。

## 方法
提供済み画像から39枚を切り抜き、単品37枚を一致率の対象とした。同じ品の別画像を含む。
炎の糸＋金貨、マナハーブ＋再生の粉の2枚は複数品が連結しており、単品一致率から除外した。
時間は39枚の認識処理。モデル読込・画面撮影・品名検出は含まない。CPU 2スレッド。
原寸・色反転・カラー3倍Lanczosを比較。Manga OCRは公式方式のグレー入力と標準生成で比較。
EasyOCRは認識器のみ・標準greedy。Mangaは同じ語彙の復号だけを使い、日本語入力文の分かち書きは不要。
「一致」はNFKC・空白除去に加えスクロール区切りの - と ・ を同一視。「厳密」は区切りを同一視しない。
辞書の近似候補による置換は点数に入れていない。画像を用いた選定結果であり、独立した未見データ評価ではない。

|候補・入力|一致 /37|厳密 /37|39枚の秒数|
|---|---:|---:|---:|
|ch_PP-OCRv5_rec_server-inverted|8|8|5.77|
|ch_PP-OCRv5_rec_server-lanczos|22|21|4.69|
|ch_PP-OCRv5_rec_server|8|8|6.00|
|easy-inverted|6|6|6.21|
|easy-lanczos|8|8|6.57|
|easy-original|1|1|7.40|
|japan_PP-OCRv4_rec_mobile-inverted|5|5|3.62|
|japan_PP-OCRv4_rec_mobile-lanczos|10|9|1.11|
|japan_PP-OCRv4_rec_mobile|4|4|4.56|
|manga|9|9|27.30|
|multi_PP-OCRv6_rec_medium-inverted|27|23|6.12|
|multi_PP-OCRv6_rec_medium-lanczos|27|23|5.00|
|multi_PP-OCRv6_rec_small-inverted|27|23|1.62|
|multi_PP-OCRv6_rec_small-lanczos|28|24|1.19|
|multi_PP-OCRv6_rec_small|26|22|1.78|

Windows標準OCRはこの検証環境では画像ファイルへのアクセス拒否で測定不可。性能の優劣は断定していない。
採用モデルは元のカラーを保持。二値化による画線の切り捨てや生成AIによる文字復元はしない。
小さい濁点・半濁点などの誤読は残る。近似名を自動確定せず、辞書候補と利用者の確認で補う。
モデルは約21.2MB。取得元URLとSHA256は models/manifest.json を参照。

## 参考資料
- [RapidOCRとモデル配布・ライセンス](https://github.com/RapidAI/RapidOCR)
- [モデル定義](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml)
- [EasyOCR](https://github.com/JaidedAI/EasyOCR)
- [Manga OCR](https://github.com/kha-white/manga-ocr)
- [Manga OCRモデル](https://huggingface.co/kha-white/manga-ocr-base)

## 再現
ソース版で python tools/benchmarks/benchmark_ocr.py を実行すると、同梱モデルの結果と時間を出力。
採用候補比較時の各行の結果は tools/benchmarks/comparison-results.json。未採用モデルとPyTorchは配布に含めない。
