"""品名の比較用の正規化。OCR名・除外名・学習名・辞書名で共通に使う。"""
import unicodedata


def normalize(text):
    """全半角と空白の差をなくし、OCR名・除外名・学習名を比較できる形にする。"""
    return ''.join(unicodedata.normalize('NFKC', text).split())
