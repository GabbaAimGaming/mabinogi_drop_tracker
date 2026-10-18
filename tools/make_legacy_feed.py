"""旧版向けDrive移行JSONを生成。GitHubのZIP URLを誤って配信しない。"""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from drop_tool.updater import drive_url, make_info


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit('使い方: python tools/make_legacy_feed.py 全体ZIP Drive共有URL 出力JSON')
    drive_url(sys.argv[2])
    info = make_info(Path(sys.argv[1]), sys.argv[2])
    Path(sys.argv[3]).write_text(json.dumps(info, ensure_ascii=False, indent=2), 'utf-8')
    print('旧版向けの更新情報を作成しました。既存Drive JSONの新版として登録してください。')
