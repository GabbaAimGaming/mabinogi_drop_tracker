"""設定タブ。撮影方法・読取方式・保存データの世代管理をまとめる。"""
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import ImageTk
from .retention import evidence_usage
from .settings import KEEP_RANGE
from .window_share import ShareUnavailable

NOTE = '#88666C'
PREVIEW_SIZE = (320, 180)


class SettingsViews:
    """既存タブの番号を変えず、末尾に設定タブを追加する。"""

    def __init__(self, app):
        self.app = app
        self.frame = ttk.Frame(app.notebook, padding=8)
        app.notebook.add(self.frame, text='設定')
        self.preview_photo = None
        from .update_view import UpdateView
        self.updates = UpdateView(app, self.frame)
        self._build_share()
        self._build_scan()
        self._build_evidence()
        self.refresh_usage()
        app.notebook.bind('<<NotebookTabChanged>>', self._fit, add='+')
        self.app.root.after(1000, self._refresh_preview)

    def _fit(self, event=None):
        """設定タブは縦に長いので、表示中だけ全体スクロールの高さを広げる。"""
        page = getattr(self.app, 'page', None)
        if page is None:
            return
        if self.app.notebook.select() == str(self.frame):
            self.app.root.update_idletasks()
            needed = self.app.notebook.winfo_y() + 60 + self.frame.winfo_reqheight()
            page.set_minimum_height(max(730, needed))
        else:
            page.set_minimum_height(730)

    # ---- 画面共有 ----
    def _build_share(self):
        box = ttk.LabelFrame(self.frame, text='画面共有（選んだウィンドウだけを撮影）', padding=10)
        box.pack(fill='x', anchor='n')
        top = ttk.Frame(box)
        top.pack(fill='x')
        left = ttk.Frame(top)
        left.pack(side='left', fill='both', expand=True)
        ttk.Checkbutton(left, text='画面共有をONにする（撮影するゲーム欄で選んだウィンドウを共有）',
                        variable=self.app.share_enabled, command=self.app.toggle_share).pack(anchor='w')
        ttk.Label(left, textvariable=self.app.share_state, wraplength=560).pack(anchor='w', pady=(6, 0))
        ttk.Label(left, wraplength=560, foreground=NOTE, text=(
            'Windowsの画面キャプチャ機能で、選んだウィンドウの映像だけを受け取ります。'
            '他のウィンドウが重なっていても、ゲームが背面にあっても読めます（最小化中は不可）。'
            '共有中はOSがウィンドウに枠を表示します。キー入力の取得やゲームへの操作は行いません。'
            '使えない環境では、これまでどおり前面のゲーム画面を撮影します。'
        )).pack(anchor='w', pady=(6, 0))
        self.preview = ttk.Label(top, text='共有中の映像はここに表示されます', width=40, anchor='center')
        self.preview.pack(side='right', padx=(10, 0))

    def _refresh_preview(self):
        """共有中かつ設定タブ表示中だけ縮小プレビューを更新する。"""
        try:
            share = self.app.share
            visible = self.app.notebook.select() == str(self.frame)
            if share is not None and share.running and visible:
                try:
                    image = share.frame()
                    image.thumbnail(PREVIEW_SIZE)
                    self.preview_photo = ImageTk.PhotoImage(image)
                    self.preview.configure(image=self.preview_photo, text='')
                except ShareUnavailable as exc:
                    self.preview_photo = None
                    self.preview.configure(image='', text=str(exc))
            elif share is None and self.preview_photo is not None:
                self.preview_photo = None
                self.preview.configure(image='', text='共有中の映像はここに表示されます')
        finally:
            self.app.root.after(1000, self._refresh_preview)

    # ---- 読取方式 ----
    def _build_scan(self):
        box = ttk.LabelFrame(self.frame, text='自動監視の読取方式', padding=10)
        box.pack(fill='x', anchor='n', pady=(8, 0))
        self.auto_reward = tk.BooleanVar(value=self.app.settings['auto_reward'])
        ttk.Checkbutton(box, text='宝箱＋ALT表示3秒の自動読取（試験機能）', variable=self.auto_reward,
                        command=lambda: self.app.change_auto_reward(self.auto_reward.get())).pack(anchor='w')
        ttk.Radiobutton(box, text='画面全体から品名を読む', value='full',
                        variable=self.app.scan_mode, command=self.app.change_scan_mode).pack(anchor='w')
        ttk.Radiobutton(box, text='画面中央から品名を読む', value='center',
                        variable=self.app.scan_mode, command=self.app.change_scan_mode).pack(anchor='w')
        ttk.Label(box, wraplength=900, foreground=NOTE, text=(
            '自動は宝箱を検出した直後、ALTの品名表示が3秒続いた時に開始します。'
            '検出精度は試験中です。未検出の場合は5秒後の手動読取を使ってください。'
            'どちらの読取方式でも箱を探すため画面全体を撮影します。'
            '成功・失敗の画像はdata/提出用サンプルへローカル保存します。'
            '通常の3周分画像整理では消えません。ZIP出力して本人が確認してから渡してください。'
        )).pack(anchor='w', pady=(6, 0))

    # ---- 品名画像の保存 ----
    def _build_evidence(self):
        box = ttk.LabelFrame(self.frame, text='品名画像（周回ごとの切り抜き）の保存', padding=10)
        box.pack(fill='x', anchor='n', pady=(8, 0))
        self.auto_delete = tk.BooleanVar(value=self.app.settings['evidence_auto_delete'])
        self.keep = tk.StringVar(value=str(self.app.settings['evidence_keep_runs']))
        ttk.Checkbutton(box, text='テキスト化・バックアップ済みの古い画像を自動で削除する',
                        variable=self.auto_delete, command=self._toggle).pack(anchor='w')
        row = ttk.Frame(box)
        row.pack(anchor='w', pady=(8, 0))
        ttk.Label(row, text='画像を保存する最大世代数（新しい確定済み周回から）：').pack(side='left')
        self.keep_box = ttk.Spinbox(row, from_=KEEP_RANGE[0], to=KEEP_RANGE[1], increment=1,
                                    textvariable=self.keep, width=6)
        self.keep_box.pack(side='left')
        ttk.Label(row, text='周').pack(side='left', padx=(4, 0))
        ttk.Button(row, text='保存して整理', command=self.save).pack(side='left', padx=10)
        ttk.Label(box, wraplength=900, foreground=NOTE, text=(
            '削除するのは「集計済み」で、全行の品名と扱いが確定し、記録とバックアップに'
            '同じ内容が残っている周回の画像だけです。確認待ち・未取得・集計対象外の周回、'
            '学習した見本画像、元のスクリーンショットは削除しません。'
            '周回の確定時と起動時に自動で整理します。削除後も統計とCSVは変わりません。'
        )).pack(anchor='w', pady=(8, 0))
        self.usage = tk.StringVar()
        ttk.Label(box, textvariable=self.usage).pack(anchor='w', pady=(6, 0))
        self._toggle()

    def _toggle(self):
        self.keep_box.configure(state='normal' if self.auto_delete.get() else 'disabled')

    def refresh_usage(self):
        count, size = evidence_usage(self.app.store)
        amount = f'{size / 1_000_000:.1f} MB' if size >= 1_000_000 else f'{size / 1000:.0f} KB'
        self.usage.set(f'現在保存している品名画像：{count}枚 / {amount}')

    def save(self):
        text = self.keep.get().strip()
        if not text.isascii() or not text.isdecimal() or not KEEP_RANGE[0] <= int(text) <= KEEP_RANGE[1]:
            messagebox.showerror('設定', f'世代数は{KEEP_RANGE[0]}～{KEEP_RANGE[1]}の整数で入力してください。')
            return False
        if not self.app.save_setting(evidence_auto_delete=bool(self.auto_delete.get()),
                                     evidence_keep_runs=int(text)):
            return False
        removed = self.app.prune_evidence()
        self.refresh_usage()
        message = '設定を保存しました。'
        if self.app.settings['evidence_auto_delete']:
            message += f'古い品名画像を{removed}枚削除しました。' if removed else '削除対象の画像はありません。'
        self.app.status.set(message)
        return True
