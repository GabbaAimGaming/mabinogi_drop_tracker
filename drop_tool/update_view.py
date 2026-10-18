"""設定から確認して同意した時だけ更新する。通信・解凍は画面スレッドを占有しない。"""
import json
from pathlib import Path
import queue
import shutil
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from .config import ROOT
from . import updater


class UpdateView:
    def __init__(self, app, parent):
        self.app = app
        self.installing = False
        self.checking = False
        self.jobs = queue.Queue()
        self.work = None
        self.dialog = None
        box = ttk.LabelFrame(parent, text='本体の更新', padding=10)
        box.pack(fill='x', pady=(0, 8))
        row = ttk.Frame(box); row.pack(fill='x')
        ttk.Label(row, text='現在のバージョン：v' + updater.VERSION).pack(side='left')
        self.button = ttk.Button(row, text='更新を確認', command=self.check)
        self.button.pack(side='right')
        self.url = tk.StringVar(value=app.settings.get('update_url', ''))
        if not self.url.get():
            try:
                self.url.set(json.loads((ROOT/'update-source.json').read_text('utf-8-sig')).get('url', ''))
            except (OSError, ValueError): pass
        self.url.set(updater.effective_source(self.url.get()))
        ttk.Label(box, text='更新情報のURL（通常は変更不要）：').pack(anchor='w', pady=(5,0))
        row = ttk.Frame(box); row.pack(fill='x')
        self.entry = ttk.Entry(row, textvariable=self.url)
        self.entry.pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='保存', command=self.save).pack(side='left', padx=(5,0))
        self.status = tk.StringVar(value='ボタンを押した時だけ確認します。ZIPの共有リンクをこの欄に入れないでください。')
        ttk.Label(box, textvariable=self.status, wraplength=800).pack(anchor='w', pady=(5,0))
        links = ttk.Frame(box); links.pack(fill='x', pady=(5, 0))
        ttk.Button(links, text='配布ページ・旧版', command=lambda: webbrowser.open(updater.RELEASES_URL)).pack(side='left')
        ttk.Button(links, text='復旧手順（GitHub）', command=lambda: webbrowser.open(updater.RECOVERY_URL)).pack(side='left', padx=5)
        ttk.Button(links, text='同梱の復旧手順', command=self.local_guide).pack(side='left')
        ttk.Button(box, text='配布者用：更新情報JSONを作成', command=self.publish).pack(anchor='e')
        app.root.after(150, self.poll)

    def save(self):
        try:
            url = self.url.get().strip()
            url = updater.effective_source(url)
            updater.download_url(url)
            self.url.set(url)
            if not self.app.save_setting(update_url=url): return False
            self.status.set('更新情報のリンクを保存しました。')
            return True
        except ValueError as exc:
            messagebox.showerror('更新先', str(exc), parent=self.app.root)
            return False

    def check(self):
        if self.checking or self.installing: return
        if not self.url.get().strip():
            messagebox.showinfo('更新先が未設定です', '配布者から案内された更新情報JSONの共有リンクを入力してください。', parent=self.app.root)
            return
        if not self.save(): return
        self.checking = True; self.button.configure(state='disabled')
        self.status.set('更新情報を確認しています…')
        url = self.url.get().strip()
        try:
            work = updater.new_work(ROOT)
        except Exception as exc:
            self.failed(str(exc)); return
        self.work = work
        def run():
            try: self.jobs.put(('checked', updater.check(url, work)))
            except Exception as exc: self.jobs.put(('error', str(exc)))
        threading.Thread(target=run, daemon=True).start()

    def offer(self, info):
        self.checking = False; self.button.configure(state='normal')
        if updater.version_key(info['version']) <= updater.version_key(updater.VERSION):
            updater.cleanup(self.work, ROOT)
            self.status.set('新しいバージョンはありません。')
            messagebox.showinfo('更新確認', '現在のバージョンは最新版です。', parent=self.app.root)
            return
        notes = info.get('release_notes', '')
        text = f"新しいバージョンがあります。\nv{updater.VERSION} → v{info['version']}\n\n{notes}\n\n更新しますか？\n更新後にツールを再起動します。履歴・学習データは引き継ぎます。"
        if not messagebox.askyesno('更新の確認', text, parent=self.app.root):
            updater.cleanup(self.work, ROOT)
            self.status.set('更新を見送りました。現在のバージョンを引き続き使えます。')
            return
        if self.app.busy or self.app.samples.lock.locked():
            messagebox.showinfo('読取・保存中です', '読取とサンプル保存が終わってから、もう一度更新を確認してください。', parent=self.app.root)
            return
        if not getattr(updater.sys, 'frozen', False):
            messagebox.showinfo('ソース版', '本体の更新はWindows配布EXEで利用してください。', parent=self.app.root)
            return
        try:
            self.app.store.save()
        except Exception as exc:
            self.failed('記録を保存できないため更新を中止しました。' + str(exc))
            return
        self.app.stop()
        self.installing = True; self.button.configure(state='disabled')
        self.dialog = tk.Toplevel(self.app.root); self.dialog.title('KarenDrop 更新準備')
        self.dialog.transient(self.app.root); self.dialog.grab_set()
        self.dialog.protocol('WM_DELETE_WINDOW', lambda: None)
        ttk.Label(self.dialog, textvariable=self.status, padding=20, wraplength=500).pack()
        self.status.set('更新ファイルを取得しています…')
        work = self.work
        def run():
            try:
                if shutil.disk_usage(ROOT).free < info['package']['size'] * 4 + 100*1024**2:
                    raise ValueError('更新用の空き容量が不足しています。')
                def progress(done, total):
                    self.jobs.put(('progress', f'取得中：{done//1048576} MB' + (f' / {total//1048576} MB' if total else '')))
                self.jobs.put(('prepared', updater.prepare(info, work, progress)))
            except Exception as exc: self.jobs.put(('error', str(exc)))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.jobs.get_nowait()
                if kind == 'checked': self.offer(value)
                elif kind == 'progress': self.status.set(value)
                elif kind == 'prepared':
                    updater.launch(value, self.work, ROOT)
                    self.app.stop_share(); self.app.root.destroy()
                    return
                elif kind == 'published':
                    self.checking = False; self.button.configure(state='normal')
                    messagebox.showinfo('更新情報を作成しました', '保存先：' + value + '\nGitHubではupdate-info.jsonという名前で新しいReleaseへ添付してください。旧版向けはドライブのZIPリンクで作成し、既存JSONを「版を管理」で差し替えてください。', parent=self.app.root)
                elif kind == 'error': self.failed(value)
        except queue.Empty: pass
        except Exception as exc: self.failed(str(exc))
        self.app.root.after(150, self.poll)

    def failed(self, text):
        self.checking = self.installing = False
        self.button.configure(state='normal')
        if self.dialog:
            self.dialog.grab_release(); self.dialog.destroy(); self.dialog = None
        self.status.set('更新できませんでした。現在のバージョンを使用できます。')
        if self.work:
            try: updater.cleanup(self.work, ROOT)
            except OSError: pass
        messagebox.showerror('更新できませんでした', text + '\n監視を続ける場合は「監視再開」を押してください。', parent=self.app.root)

    def local_guide(self):
        import os
        try:
            os.startfile(ROOT / '更新方法.txt')
        except OSError as exc:
            messagebox.showerror('復旧手順を開けません', str(exc), parent=self.app.root)

    def publish(self):
        if self.checking or self.installing: return
        package = filedialog.askopenfilename(title='配布するWindows用の全体ZIPを選択', filetypes=[('ZIP', '*.zip')], parent=self.app.root)
        if not package: return
        url = simpledialog.askstring('ZIPの共有リンク', 'このZIPのGoogleドライブ共有リンク、またはGitHub ReleasesのZIPリンクを貼り付けてください。', parent=self.app.root)
        if not url: return
        dest = filedialog.asksaveasfilename(title='更新情報を保存', initialfile='更新情報.json', defaultextension='.json', parent=self.app.root)
        if not dest: return
        self.checking = True; self.button.configure(state='disabled')
        def run():
            try:
                info = updater.make_info(package, url)
                Path(dest).write_text(json.dumps(info, ensure_ascii=False, indent=2), 'utf-8')
                self.jobs.put(('published', dest))
            except Exception as exc: self.jobs.put(('error', str(exc)))
        threading.Thread(target=run, daemon=True).start()
