"""起動入口。画面・保存・認識はdrop_toolパッケージを参照。"""
import tkinter as tk
from tkinter import messagebox
import sys
import json
import tempfile
from pathlib import Path
from drop_tool.app import App, capture

def main():
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
                report = dict(ok=True, title=root.title(), root=str(ROOT),
                              frozen=bool(getattr(sys, 'frozen', False)),
                              character=app.banner.photo.width())
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
        App(root)
    except Exception as exc:
        if '--self-test' in sys.argv:
            index = sys.argv.index('--self-test')
            Path(sys.argv[index + 1]).write_text(json.dumps(dict(ok=False, error=str(exc)), ensure_ascii=False), 'utf-8')
            root.destroy()
            raise
        root.withdraw()
        messagebox.showerror("起動できません", str(exc))
        root.destroy()
        return
    root.mainloop()

if __name__ == "__main__":
    main()
