"""登録名の検索と一括設定。画像認識・保存の処理はここに持ち込まない。"""
import tkinter as tk
from tkinter import ttk, messagebox
from .item_catalog import KINDS
from .tracker import normalize
from .item_links import resolve_name, name_key
from .item_registration import assign, unlink

CATEGORIES = {'material': '素材', 'equipment': '装備', 'enchant_scroll': 'スクロール',
              'currency': '金貨', 'currency_container': '金貨袋', 'spirit_gem': 'ジェム',
              'pass': '通行証', 'upgrade_stone': '改造石', 'pattern_fragment': '図面の欠片',
              'other': 'その他', 'user': '利用者登録'}


class ItemViews:
    """既存タブの番号を変えず、末尾にアイテム管理を追加する。"""
    def __init__(self, app):
        self.app = app
        self.frame = ttk.Frame(app.notebook, padding=8)
        app.notebook.add(self.frame, text='アイテム管理')
        ttk.Label(self.frame, text='除外設定と品名の対応付けは過去の統計・CSV出力にも反映します。元の周回記録は残ります。', wraplength=930).pack(anchor='w')
        bar = ttk.Frame(self.frame)
        bar.pack(fill='x', pady=6)
        ttk.Label(bar, text='品名検索：').pack(side='left')
        self.search = tk.StringVar()
        ttk.Entry(bar, textvariable=self.search, width=30).pack(side='left')
        self.kind = ttk.Combobox(bar, state='readonly', values=['すべて', *KINDS.values()], width=10)
        self.kind.set('すべて')
        self.kind.pack(side='left', padx=6)
        self.category = ttk.Combobox(bar, state='readonly', values=['全分類', *CATEGORIES.values()], width=16)
        self.category.set('全分類')
        self.category.pack(side='left')
        ttk.Button(bar, text='表示中を全選択', command=lambda: self.table.selection_set(self.table.get_children())).pack(side='left', padx=6)
        self.search.trace_add('write', lambda *_: self.refresh())
        self.kind.bind('<<ComboboxSelected>>', self.refresh)
        self.category.bind('<<ComboboxSelected>>', self.refresh)
        body = ttk.Frame(self.frame)
        body.pack(fill='both', expand=True)
        self.table = ttk.Treeview(body, columns=('name', 'category', 'target', 'kind'), show='headings', height=4, selectmode='extended')
        for key, title, width in [('name', '登録名（元の名前）', 310), ('category', '分類', 100), ('target','集計先',320), ('kind', '扱い', 90)]:
            self.table.heading(key, text=title)
            self.table.column(key, width=width)
        scroll = ttk.Scrollbar(body, command=self.table.yview)
        scroll.pack(side='right', fill='y')
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(fill='both', expand=True)
        bar = ttk.Frame(self.frame)
        bar.pack(fill='x', pady=6)
        for kind, label in KINDS.items():
            ttk.Button(bar, text='選択した品を' + label, command=lambda k=kind: self.set_selected(k)).pack(side='left', padx=(0, 6))
        bar = ttk.Frame(self.frame)
        bar.pack(fill='x')
        self.name = tk.StringVar()
        ttk.Label(bar,text='正式名検索：').pack(side='left')
        ttk.Entry(bar, textvariable=self.name, width=28).pack(side='left')
        self.targets = ttk.Combobox(bar,state='readonly',width=40)
        self.targets.pack(side='left',fill='x',expand=True,padx=5)
        self.name.trace_add('write',self.search_targets)
        bar = ttk.Frame(self.frame)
        bar.pack(fill='x',pady=4)
        self.policy = ttk.Combobox(bar,state='readonly',values=list(KINDS.values()),width=8)
        self.policy.set('集計');self.policy.pack(side='left')
        ttk.Button(bar,text='選択した元名の集計先を設定',command=self.link_selected).pack(side='left',padx=5)
        ttk.Button(bar,text='対応付けを解除',command=self.unlink_selected).pack(side='left')
        ttk.Button(bar, text='入力名を新規登録', command=self.register).pack(side='right')
        self.summary = tk.StringVar()
        ttk.Label(self.frame, textvariable=self.summary).pack(anchor='w', pady=4)
        self.refresh()
        self.search_targets()

    def refresh(self, event=None):
        selected = set(self.table.selection())
        self.table.delete(*self.table.get_children())
        catalog = self.app.vision.catalog
        for key, item in sorted(catalog.entries.items()):
            label = KINDS[catalog.classify(item['name'])]
            category = CATEGORIES.get(item['category'], 'その他')
            if normalize(self.search.get()) not in normalize(item['name']):
                continue
            if self.kind.get() not in ('すべて', label) or self.category.get() not in ('全分類', category):
                continue
            target = resolve_name(self.app.store.data,item['name']) if key in self.app.store.data.get('item_links',{}) else ''
            self.table.insert('', 'end', iid=key, values=(item['name'], category, target, label))
            if key in selected:
                self.table.selection_add(key)
        self.summary.set(f'登録 {len(catalog.entries)}品 / 表示 {len(self.table.get_children())}品。Ctrl・Shiftで複数選択できます。')

    def save(self, names, kind):
        if self.app.busy:
            self.app.status.set('読取が終わってからアイテム設定を変更してください。')
            return
        try:
            self.app.vision.catalog.set_policy(names, kind)
            self.app.vision.reload()
            self.app.stable.reset()
            self.refresh()
            self.app.refresh()
            self.app.status.set('保存しました。除外設定は過去の統計・CSV出力にも反映済みです。確認待ちの周回には、履歴の「設定を反映」を押してください。')
        except (OSError, ValueError) as exc:
            messagebox.showerror('アイテム設定', str(exc))

    def set_selected(self, kind):
        self.save([self.table.item(key, 'values')[0] for key in self.table.selection()], kind)

    def register(self):
        # 登録済み名を「名前だけ登録」で未確認に戻す事故を防ぐ。
        if self.app.vision.catalog.find(self.name.get()):
            self.search.set(self.name.get())
            self.app.status.set('登録済みです。一覧で扱いを選択してください。')
            return
        if self.app.busy:
            return
        name = self.name.get().strip()
        if not name:
            self.app.status.set('正式名検索欄に新しい品名を入力してください。')
            return
        kind = next(k for k,v in KINDS.items() if v == self.policy.get())
        if not messagebox.askyesno('新規登録の確認',f'正式名：{name}\n扱い：{KINDS[kind]}\n\n辞書に新しく追加しますか？',parent=self.app.root):
            return
        try:
            assign(self.app.vision.catalog,'',name,kind,new=True)
            self.after_registration()
        except (ValueError,OSError) as exc:
            messagebox.showerror('新規登録',str(exc))

    def search_targets(self,*_):
        self.targets.set('')
        self.targets.configure(values=self.app.vision.catalog.search(self.name.get()))

    def after_registration(self):
        self.app.vision.reload()
        self.refresh()
        self.search_targets()
        self.app.refresh()
        self.app.select_run()
        self.app.status.set('保存しました。対応付けによる集計は過去の確定済み周回にも反映しました。')

    def link_selected(self):
        if self.app.busy:
            return
        ids = self.table.selection()
        if len(ids)!=1 or not self.targets.get():
            self.app.status.set('元の登録名を1件選び、正式名検索の候補から集計先を選んでください。')
            return
        source = self.table.item(ids[0],'values')[0]
        target = self.targets.get()
        if name_key(source)==name_key(target):
            self.app.status.set('同じ品名です。上のボタンで扱いを設定できます。')
            return
        kind = next(k for k,v in KINDS.items() if v==self.policy.get())
        if not messagebox.askyesno('集計先の確認',f'元の名前：{source}\n集計先：{target}\n扱い：{KINDS[kind]}\n\n過去の確定済み周回にも反映します。元の名前・画像は残ります。同じ周回の重複は1回として数えます。設定しますか？',parent=self.app.root):
            return
        try:
            assign(self.app.vision.catalog,source,target,kind)
            self.after_registration()
        except (ValueError,OSError) as exc:
            messagebox.showerror('集計先',str(exc))

    def unlink_selected(self):
        if self.app.busy:
            return
        names = [self.table.item(i,'values')[0] for i in self.table.selection()
                 if i in self.app.store.data.get('item_links',{})]
        if not names:
            self.app.status.set('対応付け済みの元の登録名を選んでください。')
            return
        if not messagebox.askyesno('対応付けの解除',f'{len(names)}件の対応付けを解除しますか？\n元の登録名で集計し直します。記録や画像は削除しません。',parent=self.app.root):
            return
        try:
            unlink(self.app.vision.catalog,names)
            self.after_registration()
        except (ValueError,OSError) as exc:
            messagebox.showerror('対応付けの解除',str(exc))
