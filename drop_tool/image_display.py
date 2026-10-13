"""プレビュー表示専用。認識用の画像や保存画像は変更しない。"""
from PIL import Image

def pixel_preview(image: Image.Image, max_width: int = 850) -> Image.Image:
    """元の濃淡を残して最大4倍へ滑らかに拡大。保存画像には触れない。"""
    factor = max(1, min(4, max_width // image.width))
    return image.resize((image.width * factor, image.height * factor), Image.Resampling.LANCZOS)
