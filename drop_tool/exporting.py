"""他の人が名義と条件を確認できるCSV出力。"""
import csv
from pathlib import Path
from .tracker import Store

CSV_COLUMNS = [
    "プレイヤー名", "ダンジョン", "難易度", "ネアル", "集計済み周回",
    "未確認周回", "アイテム", "出現周回", "出現率",
]

def export_statistics(store: Store, path: str | Path) -> None:
    """データ一式の所有者名を各行に付ける。Excel向けにUTF-8 BOM付きで出力する。"""
    if not store.player_name:
        raise ValueError("プレイヤー名を入力してください。")
    contexts = sorted({(r["dungeon"], r["difficulty"], r["near"]) for r in store.data["runs"]})
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(CSV_COLUMNS)
        for context in contexts:
            count, pending, rows = store.stats(context)
            for name, hits, rate in rows:
                writer.writerow([store.player_name, *context, count, pending, name, hits, rate])
            # 素材なし・確認待ちだけでも条件と分母をCSVで確認できるよう残す。
            if not rows:
                writer.writerow([store.player_name, *context, count, pending, "", "", ""])
