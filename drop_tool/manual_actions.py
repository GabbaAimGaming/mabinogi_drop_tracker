"""手動撮影と周回内の修正（Appへ混ぜて使う）。

3秒後の撮影、撮影画像の確認・読取と周回への反映、手動読取の保存、
画像確認（統計に記録しない）、この周回だけの行の修正・分割を担当する。
保存処理の本体はmanual_reviewにあり、ここは画面との受け渡しだけを行う。
"""
import copy
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk
from .item_links import row_identity
from .history_actions import KIND
from . import manual_review


class ManualActions:
    """Appの手動撮影・修正操作。Appの属性（store、submit、epoch等）を前提にする。"""

    def save_manual_photo(self, result):
        try:
            manual_review.save_photo(self.store, result['run_id'], result['frame'])
            self.refresh()
            self.runs.selection_set(result['run_id'])
            self.select_run()
            self.status.set('撮影しました。「画像で確認・読取」でこの周回の画像を確認してください。')
        except Exception as exc:
            messagebox.showerror('撮影を保存できません', str(exc))

    def save_manual_reading(self, result):
        if not result.get('labels'):
            self.read_failed('manual', result, result['message'])
            return
        rows = self.store.persist_rows(self.active_id, result['labels'])
        self.store.record(self.active_id, rows, require_review=True)
        self.refresh()
        self.status.set('撮影・読取できました。履歴タブで品名と除外対象を確認し、この周回を確定してください。')
        self.completion_sound.play()
        self.notify_unregistered(result)
        self.submit_sample('manual_success', result.get('sample_frames', []), self.read_metadata(result))

    # [削減候補 2026-10-21] 呼び出し元なし（review_captureを呼ぶだけ）。確認後に削除
    # def test_image(self):
    #     self.review_capture()

    def countdown(self, seconds, text, mode):
        """seconds秒数えてからsubmit(mode)。textの{left}に残り秒を入れる。

        数え始めた後にepochが変われば（停止・ゲーム切替等）何もせず終える。
        """
        token = self.epoch

        def step(left):
            if token != self.epoch:
                return
            if left:
                self.status.set(text.format(left=left))
                self.root.after(1000, lambda: step(left - 1))
            else:
                self.submit(mode)
        step(seconds)

    def capture_manual(self):
        if self.busy:
            return
        target = self.display_id or self.active_id
        if not target:
            self.status.set('先に新しい周回を作るか、履歴から撮影する周回を選んでください。')
            return
        if not self.hwnd:
            self.status.set('撮影するゲームを選んでください。')
            return
        self.stop()
        self.manual_target = target
        self.countdown(3, '撮影まで{left}秒。ゲームへ戻りALTの品名を表示してください。', 'manual_photo')

        # [削減候補 2026-10-21] self.countdownへ集約した旧実装。確認後に削除
        # token = self.epoch
        #
        # def countdown(left):
        #     if token != self.epoch:
        #         return
        #     if left:
        #         self.status.set(f'撮影まで{left}秒。ゲームへ戻りALTの品名を表示してください。')
        #         self.root.after(1000, lambda: countdown(left - 1))
        #     else:
        #         self.submit('manual_photo')
        # countdown(3)

    def review_capture(self):
        if self.busy:
            return
        target = self.display_id or self.active_id
        if not target:
            self.status.set('履歴から確認する周回を選んでください。')
            return
        paths = manual_review.photos(self.store, target)
        if not paths:
            messagebox.showinfo('保存画像がありません', '確認済みの元画像は削除しています。品名がまだ画面に出ている場合は「3秒後に撮影」で撮り直してください。', parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title('この周回の撮影画像を確認・読取')
        window.transient(self.root)
        ttk.Label(window, text='画像を確認してから読み取ります。別の周回や共通の学習設定は変更しません。').pack(padx=10, pady=5)
        choice = ttk.Combobox(window, state='readonly', values=[f'画像 {i+1}/{len(paths)}' for i in range(len(paths))])
        choice.current(len(paths) // 2)
        choice.pack()
        preview = ttk.Label(window)
        preview.pack(padx=8, pady=8)

        def show(*_):
            try:
                with Image.open(paths[choice.current()]) as source:
                    shown = source.convert('RGB')
                shown.thumbnail((1050, 600))
                window.photo = ImageTk.PhotoImage(shown)
                preview.configure(image=window.photo)
            except (OSError, ValueError) as exc:
                messagebox.showerror('画像', str(exc), parent=window)

        def read():
            if self.busy:
                return
            try:
                with Image.open(paths[choice.current()]) as source:
                    frame = source.convert('RGB')
                run = self.store.find(target)
                self.saved_read_target = target
                self.saved_read_expected = copy.deepcopy({'rows': run['rows'], 'status': run['status']})
                self.stop()
                window.destroy()
                self.submit('saved_read', frame)
            except Exception as exc:
                messagebox.showerror('画像を読み取れません', str(exc), parent=self.root)
        choice.bind('<<ComboboxSelected>>', show)
        show()
        ttk.Button(window, text='この画像を読み取る', command=read).pack(pady=8)

    def apply_saved_read(self, result):
        if not result.get('labels'):
            messagebox.showinfo('読取できませんでした', '元の記録は保持しています。撮影画像の品名表示を確認してください。', parent=self.root)
            return
        if not messagebox.askyesno('この周回へ反映', f"{len(result['labels'])}行を読み取りました。選んだ周回の品名を置き換え、確認待ちに戻しますか？\n他の周回や学習設定は変更しません。", parent=self.root):
            return
        try:
            manual_review.replace_reading(self.store, result['run_id'], result, result['expected'])
            self.refresh()
            self.runs.selection_set(result['run_id'])
            self.select_run()
            self.notebook.select(1)
            self.status.set('この周回に読み取り結果を反映しました。内容を確認して確定してください。')
        except Exception as exc:
            messagebox.showerror('反映できません', str(exc), parent=self.root)

    # [削減候補 2026-10-21] 本体からの呼び出し元なし（旧呼び出し用。手動操作はcapture_manual）。
    # 使うのはtests/test_capture_flowの1件だけで、そちらもコメントアウト済み。確認後に削除
    # def timed_read(self):
    #     """旧呼び出し用の直接読取。通常の手動操作はcapture_manualから行う。"""
    #     if not self.hwnd:
    #         self.status.set('撮影するゲームを選んでください。')
    #         return
    #     if not self.active_id or self.store.find(self.active_id)['status'] != 'waiting':
    #         self.status.set('先に「新しい周回」、または未取得の履歴を選んで「監視再開」を押してください。')
    #         return
    #     if self.busy:
    #         self.status.set('読取処理中です。下の監視表示で進行状況を確認してください。')
    #         return
    #     self.stop()
    #     token = self.epoch
    #
    #     def countdown(left):
    #         if token != self.epoch:
    #             return
    #         if left:
    #             self.status.set(f'報酬読取まで {left}秒。ゲームへ戻ってALTを押し続けてください。')
    #             self.root.after(1000, lambda: countdown(left - 1))
    #         else:
    #             self.status.set('報酬を撮影・読取中です。')
    #             self.submit('manual')
    #     countdown(5)

    def show_test(self, result):
        text = '\n'.join((f"{KIND[r['kind']]}：{r['name']}" for r in result['labels']))
        messagebox.showinfo('画像確認（統計には記録しません）', text or result['message'])

    def edit_this_run(self):
        if self.busy:
            return
        selection = self.rows.selection()
        if not selection or not self.display_id:
            self.status.set('先に履歴から修正する行を選んでください。')
            return
        run_id = self.display_id
        index = int(selection[0])
        run = self.store.find(run_id)
        original = copy.deepcopy(run['rows'])
        name, kind = row_identity(self.store.data, run['rows'][index])
        window = tk.Toplevel(self.root)
        window.title('この周回だけ修正・分割')
        window.transient(self.root)
        ttk.Label(window, text='正しい品名を1行に1品入力。結合された行は改行して分割できます。\n空欄で保存すると、この行をこの周回から除きます。共通学習は変更しません。').pack(padx=12, pady=8)
        text = tk.Text(window, width=55, height=5)
        text.insert('1.0', name)
        text.pack(padx=12)
        policy = ttk.Combobox(window, state='readonly', values=list(KIND.values()))
        policy.set(KIND[kind])
        policy.pack(pady=6)

        def save():
            try:
                current = self.store.find(run_id)
                if current['rows'] != original:
                    raise ValueError('周回の内容が変わりました。開き直してください。')
                names = [n.strip() for n in text.get('1.0', 'end').splitlines() if n.strip()]
                selected = next(k for k, v in KIND.items() if v == policy.get())
                summary = '\n'.join(names) if names else 'この行を除く'
                if not messagebox.askyesno('この周回だけ変更', summary + '\n扱い：' + policy.get() + '\n\nこの周回だけ変更して確認待ちに戻しますか？', parent=window):
                    return
                manual_review.edit_row(self.store, run_id, index, names, selected)
                window.destroy()
                self.refresh()
                self.runs.selection_set(run_id)
                self.select_run()
                self.status.set('この周回だけ修正しました。共通の対応付け・学習設定は変更していません。')
            except Exception as exc:
                messagebox.showerror('修正できません', str(exc), parent=window)
        ttk.Button(window, text='この周回だけ保存', command=save).pack(pady=10)
