"""品名ではない、完全な百分率表示・時刻表示だけを取り除く。"""
import re
from .names import normalize

def is_hud_text(text):
    text=normalize(text)
    # 数字入り装備名や数量付き品名、単独数字はこの条件に含めない。
    if re.fullmatch(r'(?:\d{1,3}(?:\.\d+)?%){1,4}',text):
        return all(0<=float(value)<=100 for value in re.findall(r'(\d+(?:\.\d+)?)%',text))
    match=re.fullmatch(r'(?:午前|午後)?(\d{1,2}):(\d{2})(?::(\d{2}))?',text)
    return bool(match and int(match[1])<24 and int(match[2])<60
                and (match[3] is None or int(match[3])<60))


def is_system_notice(text):
    """赤文字の所持品取得ログを品名として登録しない。曖昧な断片は残す。"""
    text=normalize(text)
    return bool(re.search(r'を拾った[。.!！]?$',text)
                or re.match(r'^[<〈\[]\s*(?:SYSTEM|COMBAT)\s*[>〉\]]',text,re.I))
