"""CSV比較専用の2タブ。自分の生の周回記録とは混ぜず、読込済みCSVだけを表示する。"""
import tkinter as tk
import csv
from tkinter import ttk, filedialog, messagebox
from .csv_collection import CsvCollection, load_batch, key, filter_groups, COMBINED_LABEL


class CsvViews:
    def __init__(self, notebook, folder):
        self.collection = CsvCollection(folder)
        self.views = []
        for personal, title in ((True, 'CSV：プレイヤー別'), (False, 'CSV：全体集計')):
            frame = ttk.Frame(notebook, padding=8)
            notebook.add(frame, text=title)
            bar = ttk.Frame(frame)
            bar.pack(fill='x')
            ttk.Button(bar, text='CSVを読み込む', command=self.import_files).pack(side='left')
            player = ttk.Combobox(bar, state='readonly', width=20) if personal else None
            if player is not None:
                player.pack(side='left', padx=8)
                player.bind('<<ComboboxSelected>>', lambda event: self.refresh())
                ttk.Button(bar, text='この人の読込データを削除', command=self.remove_player).pack(side='left')
            context = ttk.Combobox(frame, state='readonly', width=60)
            context.pack(anchor='w', pady=6)
            context.bind('<<ComboboxSelected>>', lambda event: self.render())
            summary = tk.StringVar()
            ttk.Label(frame, textvariable=summary).pack(anchor='w')
            table_frame = ttk.Frame(frame)
            table_frame.pack(fill='both', expand=True, pady=6)
            table = ttk.Treeview(table_frame, columns=('context','item','hits','count','rate'),
                                 show='headings', height=5)
            for name, text, width in [('context','ダンジョン / 難易度 / ネアル',260),
                    ('item','アイテム',250),('hits','出現周回',90),('count','集計済み周回',105),('rate','ドロップ率',95)]:
                table.heading(name, text=text)
                table.column(name, width=width, minwidth=60)
            scroll = ttk.Scrollbar(table_frame, orient='vertical', command=table.yview)
            scroll.pack(side='right', fill='y')
            table.configure(yscrollcommand=scroll.set)
            table.pack(fill='both', expand=True)
            ttk.Label(frame, text='読込済みCSVのみ集計。同名・同条件は後から読み込む内容に置換します。', wraplength=850).pack(anchor='w')
            ttk.Label(frame, text='合算率＝出現周回の合計÷集計済み周回の合計。アルビ＋夢幻ラビ誘惑はアルビ全難易度と夢幻ラビ誘惑が対象。', wraplength=850).pack(anchor='w')
            self.views.append(dict(player=player, context=context, summary=summary, table=table, contexts=[]))
        self.refresh()

    def refresh(self):
        players = sorted({g['player'] for g in self.collection.groups})
        for view in self.views:
            player = view['player']
            if player is not None:
                previous = player.get()
                player.configure(values=players)
                player.set(previous if previous in players else (players[0] if players else ''))
            groups = self.collection.aggregate(player.get() if player is not None else None)
            view['contexts'] = sorted(groups)
            # 未読込でも合算の選択肢を示し、読込後は条件別の候補も追加する。
            dungeons = sorted({c[0] for c in groups})
            choices = ['全エリア', COMBINED_LABEL] + [d + '（ダンジョン合算）' for d in dungeons] + [' / '.join(c) for c in view['contexts']]
            view['filters'] = [('all', None), ('combined', None)] + [('dungeon', d) for d in dungeons] + [('context', c) for c in view['contexts']]
            selected = view['context'].get()
            view['context'].configure(values=choices)
            view['context'].set(selected if selected in choices else choices[0])
        self.render()

    def render(self):
        for view in self.views:
            player = view['player']
            groups = self.collection.aggregate(player.get() if player is not None else None)
            index = view['context'].current()
            mode, value = view['filters'][max(index, 0)]
            groups = filter_groups(groups, mode, value)
            table = view['table']
            table.delete(*table.get_children())
            count = sum(g['count'] for g in groups.values())
            pending = sum(g['pending'] for g in groups.values())
            view['summary'].set(f'{len(groups)}集計区分 / 集計済み {count}周 / 未確認 {pending}周（分母から除外）')
            for context, group in sorted(groups.items()):
                items = sorted(group['items'].items(), key=lambda pair: (-pair[1], pair[0]))
                if not items:
                    table.insert('', 'end', values=(' / '.join(context),'集計対象の品なし','—',group['count'],'—'))
                for item, hits in items:
                    rate = f"{hits / group['count']:.2%}" if group['count'] else '—'
                    table.insert('', 'end', values=(' / '.join(context), item, hits, group['count'], rate))

    def import_files(self):
        paths = filedialog.askopenfilenames(title='名義付きのドロップ記録CSVを選択', filetypes=[('CSV','*.csv')])
        if not paths:
            return
        try:
            incoming = load_batch(paths)
            previous = {key(g): g for g in self.collection.groups}
            changes = [g for g in incoming if key(g) in previous and previous[key(g)] != g]
            if changes:
                details = '\n'.join(' / '.join(key(g)) + f"：{previous[key(g)]['count']}周 → {g['count']}周" for g in changes)
                if not messagebox.askyesno('累積CSVを置き換えます',
                    '以下の名義・条件を丸ごと置き換えます。古いCSVだと件数が減ることもあります。\n\n' + details):
                    return
            self.collection.replace(incoming)
            self.refresh()
            messagebox.showinfo('CSV読込完了', f'{len(incoming)}件の名義・条件を読み込みました。同じデータは加算していません。')
        except (OSError, ValueError, KeyError, TypeError, csv.Error) as exc:
            messagebox.showerror('CSVを読み込めません', str(exc))

    def remove_player(self):
        player = self.views[0]['player'].get()
        if not player:
            return
        if messagebox.askyesno('CSV読込データを削除', f'{player} のCSV読込データを削除しますか？元CSVと周回履歴は残ります。'):
            try:
                self.collection.remove_player(player)
                self.refresh()
            except OSError as exc:
                messagebox.showerror('削除できません', str(exc))
