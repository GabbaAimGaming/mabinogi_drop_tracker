"""起動入口。画面・保存・認識はdrop_toolパッケージを参照。"""
import tkinter as tk
from tkinter import messagebox
import sys
import json
import tempfile
from pathlib import Path
from drop_tool.app import App, capture

def run_app(guard=None):
    capture.configure_dpi()
    root = tk.Tk()
    try:
        if '--self-test' in sys.argv:
            # 配布ビルドの検証専用。実データを作らず画面・画像・保存先を確認する。
            from drop_tool.tracker import Store
            from drop_tool.config import ROOT
            root.withdraw()
            with tempfile.TemporaryDirectory() as folder:
                app = App(root, Store(folder))
                root.update_idletasks()
                from drop_tool.ocr_engine import probe
                ocr_name = probe()
                from drop_tool.chest_detector import ChestDetector
                from drop_tool.preflight import check_assets
                check_assets(ROOT)
                detector = ChestDetector()
                from drop_tool.near_dialog import NearDialogDetector
                from PIL import Image
                near = NearDialogDetector()
                dialog = Image.new('RGB', (403, 214), (35, 35, 35))
                for name, pos in (('question', (84, 77)), ('buttons', (105, 155))):
                    with Image.open(ROOT / 'assets/near-dialog' / (name + '.png')) as feature:
                        dialog.paste(feature, pos)
                if not near.detect(dialog):
                    raise ValueError('ネアル確認画面の検出資産を確認できません。')
                report = dict(ocr=ocr_name, ok=True, title=root.title(), root=str(ROOT),
                              update_button=app.settings_views.updates.button.cget('text'),
                              near_dialog=True,
                              chest_templates=len(detector.templates),
                              frozen=bool(getattr(sys, 'frozen', False)),
                              character=app.banner.photo.width(),
                              registered_items=len(app.vision.catalog.entries),
                              item_tab=app.notebook.tab(app.item_views.frame, "text"))
                index = sys.argv.index('--self-test')
                Path(sys.argv[index + 1]).write_text(json.dumps(report, ensure_ascii=False), 'utf-8')
            root.destroy()
            return
        if '--diagnose' in sys.argv:
            root.withdraw()
            from drop_tool.preflight import inspect
            from drop_tool.config import ROOT
            lines, fatal = inspect()
            text = '\n'.join(lines)
            try:
                (ROOT / '環境診断.txt').write_text(text, 'utf-8')
            except OSError:
                text += '\n診断ファイルを保存できませんでした。'
            messagebox.showinfo('環境診断', text, parent=root)
            root.destroy()
            return
        if guard:
            guard.mark_window(root)
        App(root)
    except Exception as exc:
        if '--self-test' in sys.argv:
            index = sys.argv.index('--self-test')
            Path(sys.argv[index + 1]).write_text(json.dumps(dict(ok=False, error=str(exc)), ensure_ascii=False), 'utf-8')
            root.destroy()
            return 1
        root.withdraw()
        messagebox.showerror("起動できません", str(exc))
        root.destroy()
        return
    root.mainloop()


def main():
    # 診断・更新後の自己診断は一時データだけを使用する。
    if '--self-test' in sys.argv or '--diagnose' in sys.argv:
        return run_app()
    from drop_tool.config import ROOT
    from drop_tool.instance_guard import InstanceGuard
    executable = Path(sys.executable) if getattr(sys, 'frozen', False) else ROOT / 'app.py'
    guard = InstanceGuard(executable, ROOT / 'data')
    try:
        if not guard.acquire():
            guard.activate_existing()
            return 0
        return run_app(guard)
    except OSError as exc:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror('起動できません', '二重起動の確認ができないため、記録保護のため起動を中止しました。\n' + str(exc), parent=root)
        root.destroy()
        return 1
    finally:
        guard.close()

if __name__ == "__main__":
    sys.exit(main())
