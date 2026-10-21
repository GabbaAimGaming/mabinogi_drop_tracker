"""「周回履歴・確認待ち」と「ドロップ統計」の操作（Appへ混ぜて使う）。

履歴と統計の表示更新、行の選択・プレビュー、辞書への登録（item_registration.assign）、
周回の確定・対象外・削除、CSV出力、未登録名の通知、アイテム設定の反映を担当する。
画面部品（self.runs、self.rows、self.preview等）はui.build_widgetsがAppへ設定する。
"""
from tkinter import messagebox, filedialog
from PIL import Image, ImageTk
from .exporting import export_statistics
from .image_display import pixel_preview
from .label_images import ocr_image
from .item_links import row_identity, name_key
from .item_registration import assign

STATUS = {'waiting': '未取得', 'review': '確認待ち', 'confirmed': '集計済み', 'discarded': '集計対象外'}
KIND = {'material': '集計', 'excluded': '除外', 'review': '要確認'}


class HistoryActions:
    """Appの履歴・統計操作。Appの属性（store、vision、画面部品）を前提にする。"""

    def refresh(self):
        current = self.runs.selection()
        self.runs.delete(*self.runs.get_children())
        for r in reversed(self.store.data['runs']):
            self.runs.insert('', 'end', iid=r['id'], values=(r['created'], f"{r['dungeon']} / {r['difficulty']} / {r['near']}", STATUS[r['status']]))
        if current and self.runs.exists(current[0]):
            self.runs.selection_set(current[0])
        self.contexts = sorted({(r['dungeon'], r['difficulty'], r['near']) for r in self.store.data['runs']})
        old = self.groups.get()
        self.groups.configure(values=[' / '.join(c) for c in self.contexts])
        if old in self.groups['values']:
            self.groups.set(old)
        elif self.contexts:
            self.groups.current(0)
        else:
            self.groups.set('')
        self.refresh_stats()

    def refresh_stats(self):
        self.stats_table.delete(*self.stats_table.get_children())
        i = self.groups.current()
        if i < 0:
            self.summary.set('まだ記録がありません。入場時に新しい周回を開始してください。')
            return
        n, pending, rows = self.store.stats(self.contexts[i])
        self.summary.set(f'集計済み {n}周 / 未取得・確認待ち {pending}周（分母から除外）')
        for name, count, rate in rows:
            self.stats_table.insert('', 'end', values=(name, count, f'{rate * 100:.2f}%'))

    def select_run(self, event=None):
        ids = self.runs.selection()
        if not ids:
            return
        self.display_id = ids[0]
        run = self.store.find(self.display_id)
        self.rows.delete(*self.rows.get_children())
        self.preview.configure(image='')
        self.page.set_minimum_height(730)
        self.correct.set('')
        self.candidates.set('')
        self.search_candidates()
        for i, row in enumerate(run['rows']):
            target, kind = row_identity(self.store.data, row)
            shown = row['name'] if target == row['name'] else row['name'] + ' → ' + target
            self.rows.insert('', 'end', iid=str(i), values=(shown, KIND[kind]))

    def select_row(self, event=None):
        """元の切り抜きを滑らかに拡大。白黒比較は表示だけに適用する。"""
        selected = self.rows.selection()
        if not selected or not self.display_id:
            return
        run = self.store.find(self.display_id)
        row = run['rows'][int(selected[0])]
        self.correct.set(row['name'])
        self.candidates.set('')
        self.candidates.configure(values=self.vision.catalog.search(row['name']))
        if not row.get('image') or not (self.store.folder / row['image']).is_file():
            self.photo = None
            self.preview.configure(image='')
            self.page.set_minimum_height(730)
            if run.get('evidence_pruned'):
                self.status.set('この行の画像は保存世代を過ぎたため削除済みです。品名と扱いはテキストで保存されています。')
            else:
                self.status.set('この行の画像が見つかりません。品名と扱いはテキストで保存されています。')
            return
        # ファイルを開いたままにすると、Windowsでは画像の整理・削除が失敗する。
        with Image.open(self.store.folder / row['image']) as source:
            image = source.convert('RGB')
        shown = ocr_image(image) if self.clean_preview.get() else image
        self.photo = ImageTk.PhotoImage(pixel_preview(shown))
        self.preview.configure(image=self.photo)
        self.page.set_minimum_height(730 + self.photo.height())

    def search_candidates(self, *_):
        """検索するだけでは登録しない。検索の変更で前の候補選択を解除する。"""
        self.candidates.set('')
        self.candidates.configure(values=self.vision.catalog.search(self.correct.get()))

    def correct_row(self, kind=None, *, new=False):
        """選択した正式名への対応付けを確認して保存する。元の観測名は残す。"""
        if self.busy:
            return
        selected = self.rows.selection()
        if not selected or not self.display_id:
            self.status.set('先に履歴から読み取った行を選んでください。')
            return
        try:
            from .item_catalog import KINDS
            if kind is None:
                kind = next(k for k,v in KINDS.items() if v == self.registration_kind.get())
            run = self.store.find(self.display_id)
            row = run['rows'][int(selected[0])]
            target = self.correct.get().strip() if new else self.candidates.get().strip()
            if not target:
                raise ValueError('新規登録は検索欄に正式名を入力し、既存品は辞書候補から選択してください。')
            if new and self.vision.catalog.find(target):
                raise ValueError('登録済みの品名です。辞書候補から選択してください。')
            detail = ('新しい正式名として登録' if new else '選択した辞書の品へ登録')
            text = (f"元の読み取り名：{row['name']}\n登録先：{target}\n扱い：{KINDS[kind]}\n\n{detail}しますか？")
            if row['name'] != '読取不明' and name_key(row['name']) != name_key(target):
                text += '\nこの誤登録名を含む過去の確定済み周回も、登録先の扱いで集計します。元の名前・画像は残ります。'
            text += '\n周回の確定は、登録後に内容を確認して行ってください。'
            if not messagebox.askyesno('登録内容の確認',text,parent=self.root):
                return
            image = None
            if row.get('image') and (self.store.folder / row['image']).is_file():
                with Image.open(self.store.folder / row['image']) as source:
                    image = source.convert('RGB')
            assign(self.vision.catalog, row['name'], target, kind, new=new,
                   run_id=self.display_id, row_index=int(selected[0]), image=image)
            self.vision.reload()
            self.refresh()
            self.select_run()
            self.item_views.refresh()
            self.status.set('登録しました。元の読み取り名を残して、選んだ正式名へ対応付けます。履歴を確認して周回を確定してください。')
        except Exception as exc:
            messagebox.showerror('登録', str(exc))

    def confirm_run(self):
        if not self.display_id:
            return
        try:
            self.store.confirm(self.display_id)
            self.refresh()
            self.prune_evidence()
        except Exception as exc:
            messagebox.showerror('確定', str(exc))

    def discard(self):
        if not self.display_id:
            return
        if messagebox.askyesno('集計対象外', 'この周回を統計から外しますか？記録自体は残ります。'):
            self.store.find(self.display_id)['status'] = 'discarded'
            self.store.save()
            self.refresh()

    def delete_runs(self):
        """記録を削除する。学習設定は残し、保存失敗時は元の周回を復元する。"""
        ids = self.runs.selection()
        if not ids:
            messagebox.showinfo('周回を削除', '履歴から削除する周回を選んでください。')
            return
        if not messagebox.askyesno('周回を削除', f'選択した {len(ids)}周を履歴と集計から削除しますか？\n覚えたアイテム名は残ります。'):
            return
        try:
            count = self.store.delete_runs(ids)
            if self.active_id in ids:
                self.stop()
                self.active_id = None
            if self.display_id in ids:
                self.display_id = None
                self.rows.delete(*self.rows.get_children())
                self.preview.configure(image='')
                self.correct.set('')
            self.refresh()
            self.status.set(f'{count}周を履歴と集計から削除しました。学習内容は保持しています。')
        except Exception as exc:
            messagebox.showerror('削除できません', str(exc))

    def save_player_name(self):
        """この記録ファイルの所有者名を保存する。周回や学習内容には触れない。"""
        try:
            self.store.set_player_name(self.player_name.get())
            self.player_name.set(self.store.player_name)
            return True
        except (ValueError, OSError) as exc:
            self.status.set('プレイヤー名を保存できません：' + str(exc))
            return False

    def export(self):
        """名義を保存してから、確認済み統計をExcel向けUTF-8 CSVに出力する。"""
        if not self.save_player_name():
            return
        if not self.store.player_name:
            messagebox.showinfo('プレイヤー名', 'CSVに載せるプレイヤー名を入力してください。')
            return
        path = filedialog.asksaveasfilename(defaultextension='.csv', initialfile='drop-statistics.csv')
        if not path:
            return
        try:
            export_statistics(self.store, path)
            self.status.set('プレイヤー名付きのCSVを保存しました。')
        except (ValueError, OSError) as exc:
            messagebox.showerror('CSVを保存できません', str(exc))

    def notify_unregistered(self, result):
        """保存済みの1周につき1回だけ、未登録名をまとめて知らせる。"""
        names = sorted({x['name'] for x in result['labels'] if x.get('registered') is False})
        if not names:
            return
        self.notebook.select(1)
        self.runs.selection_set(self.active_id)
        self.select_run()
        messagebox.showinfo('未登録の品名があります',
            f'{len(names)}種類の未登録候補があります。画像と辞書候補を確認してください。\n'
            '名前だけ登録し、扱いを未確認のまま残すこともできます。\n\n'
            + '\n'.join(names[:10]) + ('\n…' if len(names) > 10 else ''), parent=self.root)

    def apply_item_settings(self):
        """確認待ちの選択周回に限り、利用者の明示操作で現在の設定を適用する。"""
        if self.busy or not self.display_id:
            return
        try:
            self.vision.catalog.apply_pending(self.display_id)
            self.select_run()
            self.refresh()
            self.status.set('設定を反映しました。画像と品名を確認してから周回を確定してください。')
        except (OSError, ValueError) as exc:
            messagebox.showerror('設定を反映', str(exc))
