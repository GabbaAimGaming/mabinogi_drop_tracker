import queue
import threading
import traceback
import time
import tkinter as tk
from tkinter import messagebox, filedialog
from PIL import Image, ImageTk
from .notification import CompletionSound
from .exporting import export_statistics
from .image_display import pixel_preview
from .label_images import ocr_image
from .tracker import ROOT, Store, StableReading, default_near
from .vision import Vision
from . import windows_capture as capture
STATUS = {'waiting': '未取得', 'review': '確認待ち', 'confirmed': '集計済み', 'discarded': '集計対象外'}
KIND = {'material': '集計', 'excluded': '除外', 'review': '要確認'}

class App:
    """Tkの操作画面。画像処理をワーカーへ渡し、結果はTk側で反映する。"""

    def _build_widgets(self):
        """レイアウトを専用モジュールへ委譲し、読取の状態管理と分離する。"""
        from .ui import build_widgets
        build_widgets(self)

    def __init__(self, root, store=None):
        """記録・認識器と監視状態を初期化し、画面構築後にTkの定期処理を開始する。"""
        self.root = root
        root.title('カレンとドロップ記録 v0.12')
        root.geometry('1020x760')
        root.minsize(780, 600)
        from .theme import apply_theme
        apply_theme(root)
        self.store = store or Store()
        self.completion_sound = CompletionSound(self.store.folder)
        self.sound_enabled = tk.BooleanVar(value=self.completion_sound.enabled)
        self.vision = Vision(self.store)
        self.stable = StableReading()
        root.report_callback_exception = self.callback_error
        self.active_id = None
        self.hwnd = None
        self.busy = False
        self.watching = False
        self.jobs = queue.Queue()
        self.epoch = 0
        self.windows = []
        self.display_id = None
        self.worker_phase = ''
        self.worker_started = 0
        self.last_diagnostic = ''
        self.read_attempts = 0
        self.last_context = ('アルビ', 'HD')
        self.status = tk.StringVar(value='ゲームを選択し、入場時に「新しい周回」を押してください。')
        self.summary = tk.StringVar()
        self.diagnostic = tk.StringVar(value='監視：停止中')
        self.player_name = tk.StringVar(value=self.store.player_name)
        self._build_widgets()
        self.refresh_windows()
        self.refresh()
        root.after(150, self.poll)
        root.after(350, self.tick)
        root.after(3000, self.auto_window)

    def change_sound(self):
        try:
            self.completion_sound.set_enabled(self.sound_enabled.get())
        except OSError as exc:
            self.sound_enabled.set(self.completion_sound.enabled)
            messagebox.showerror('音の設定を保存できません', str(exc))

    def context_changed(self, event=None):
        context = (self.dungeon.get(), self.difficulty.get())
        if context != self.last_context:
            self.near.set(default_near(*context))
            self.last_context = context

    def callback_error(self, kind, error, tb):
        detail = ''.join(traceback.format_exception(kind, error, tb))
        try:
            with (self.store.folder / 'errors.log').open('a', encoding='utf-8') as f:
                f.write(detail + '\n')
        except OSError:
            pass
        self.status.set('画面処理でエラー：' + str(error) + '（data/errors.log に詳細）')

    def refresh_windows(self):
        self.windows = capture.windows()
        self.window.configure(values=[f'{name} [{hwnd}]' for hwnd, name in self.windows])
        target = self.hwnd if any((h == self.hwnd for h, _ in self.windows)) else capture.game_window(self.windows, capture.user32.GetForegroundWindow())
        if target:
            index = next((i for i, (hwnd, _) in enumerate(self.windows) if hwnd == target))
            self.window.current(index)
            if target != self.hwnd:
                self.choose_window()
                self.status.set('マビノギを選択しました。入場時に「新しい周回」を押してください。')
        else:
            self.window.set('')
            self.hwnd = None
            self.status.set('マビノギの起動を待っています。別のタイトルの場合は一覧から選んでください。')

    def auto_window(self):
        try:
            if not self.hwnd or not capture.user32.IsWindow(self.hwnd):
                self.refresh_windows()
        finally:
            self.root.after(3000, self.auto_window)

    def choose_window(self, event=None):
        index = self.window.current()
        if index >= 0:
            self.hwnd = self.windows[index][0]
            self.epoch += 1
            self.stable.reset()
    
    def new_run(self):
        """利用者の入場操作で周回を作る。報酬が同じでも別の周回として扱う。"""
        try:
            if self.active_id and self.store.find(self.active_id)['status'] == 'waiting':
                if not messagebox.askyesno('未取得の周回', '前の周回は未取得のまま履歴に残します。新しい周回を始めますか？'):
                    return
            if not self.hwnd:
                raise ValueError('撮影するゲームを選んでください。')
            run = self.store.new_run(self.dungeon.get(), self.difficulty.get(), self.near.get())
            self.active_id = run['id']
            self.epoch += 1
            self.stable.reset()
            self.watching = True
            self.status.set('監視中。クリア後、自分の宝箱を開け、拾う前にALTを押したまま待ってください。')
            self.refresh()
        except Exception as exc:
            messagebox.showerror('開始できません', str(exc))

    def stop(self):
        self.watching = False
        self.epoch += 1
        self.stable.reset()
        self.status.set('監視を停止しました。記録と学習データは保持しています。')

    def resume(self):
        selection = self.runs.selection()
        if selection and self.store.find(selection[0])['status'] == 'waiting':
            self.active_id = selection[0]
        if not self.active_id or self.store.find(self.active_id)['status'] != 'waiting':
            messagebox.showinfo('監視再開', '未取得の周回を履歴で選ぶか、新しい周回を開始してください。')
            return
        self.epoch += 1
        self.stable.reset()
        self.watching = True
        self.status.set('同じ周回の監視を再開しました。ゲームへ戻ってください。')

    def tick(self):
        """前景ゲームを定期撮影する。キー状態を取得できなくても監視を継続する。"""
        try:
            if self.busy:
                state = f'監視：{self.worker_phase}（{int(time.monotonic() - self.worker_started)}秒）'
            elif not self.watching:
                state = '監視：停止中'
            elif not self.active_id:
                state = '監視：周回未選択。「新しい周回」を押してください。'
            elif self.store.find(self.active_id)['status'] != 'waiting':
                state = '監視：取得済み。履歴で確認してください。'
            elif not capture.active(self.hwnd):
                state = '監視：ゲームが手前になるのを待っています。'
                self.stable.reset()
            else:
                state = '監視：画面の品名表示を探しています（ALTキー検出不要）。'
                self.submit('live')
            self.set_diagnostic(state)
        except Exception as exc:
            self.stable.reset()
            self.status.set('読取エラー：' + str(exc))
        finally:
            self.root.after(700, self.tick)

    def set_diagnostic(self, text):
        self.diagnostic.set(text + f' / 読取開始 {self.read_attempts}回')
        key = text.split('（')[0]
        if key == self.last_diagnostic:
            return
        self.last_diagnostic = key
        try:
            path = self.store.folder / 'monitor.log'
            if path.exists() and path.stat().st_size > 200000:
                path.write_text('', encoding='utf-8')
            with path.open('a', encoding='utf-8') as f:
                f.write(time.strftime('%H:%M:%S ') + text + '\n')
        except OSError:
            pass

    def submit(self, mode, image=None):
        """撮影と認識をワーカーで実行する。Tkのウィジェットは触らない。"""
        if self.busy:
            return
        self.busy = True
        epoch = self.epoch
        hwnd = self.hwnd
        self.worker_started = time.monotonic()
        self.worker_phase = '画面を撮影中'
        if mode in ('live', 'manual'):
            self.read_attempts += 1

        def work():
            try:
                frame = image if image is not None else capture.capture(hwnd)
                if mode in ('live', 'manual'):
                    frame.save(self.store.folder / 'last-loot-capture.png')
                self.worker_phase = '撮影済み・ALTの品名を認識中'
                result = self.vision.analyze(frame)
                self.jobs.put((epoch, mode, result, None))
            except Exception as exc:
                self.jobs.put((epoch, mode, None, str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        """結果の世代番号を照合し、停止や周回変更前の結果を破棄する。"""
        try:
            while True:
                epoch, mode, result, error = self.jobs.get_nowait()
                self.busy = False
                if epoch != self.epoch:
                    continue
                if error:
                    self.status.set('読取できません：' + error)
                    self.stable.reset()
                    continue
                if mode == 'test':
                    self.show_test(result)
                elif mode == 'manual':
                    if not result.get('labels'):
                        self.status.set('撮影できましたが、報酬を登録できません：' + result['message'])
                    else:
                        rows = self.store.persist_rows(self.active_id, result['labels'])
                        for row in rows:
                            row['kind'] = 'review'
                        self.store.record(self.active_id, rows)
                        self.refresh()
                        self.status.set('撮影・読取できました。履歴タブで品名と除外対象を確認し、この周回を確定してください。')
                        self.completion_sound.play()
                else:
                    # 撮影中の画面切替も再確認し、別ウィンドウへ移った結果を採用しない。
                    if not self.watching or not capture.active(self.hwnd):
                        self.stable.reset()
                        continue
                    if self.stable.observe(result):
                        self.save_live_reading(self.stable.finish())
                    else:
                        self.status.set(result['message'] + ' / 同じ品名表示を3回確認中。')
        except queue.Empty:
            pass
        except Exception as exc:
            self.callback_error(type(exc), exc, exc.__traceback__)
        finally:
            self.root.after(150, self.poll)

    def save_live_reading(self, result):
        """キー解放を待たず1周1回保存する。道中の品との区別は利用者が確認する。"""
        rows = self.store.persist_rows(self.active_id, result['labels'])
        # 名前の学習と除外は保持しつつ、報酬かどうかの確認前には集計しない。
        self.store.record(self.active_id, rows, require_review=True)
        self.watching = False
        self.refresh()
        self.status.set('読取完了。ALTを離して構いません。履歴で宝箱の報酬か確認し、周回を確定してください。')
        self.completion_sound.play()

    def test_image(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(initialdir=ROOT / 'references', filetypes=[('画像', '*.png *.jpg *.bmp')])
        if path:
            self.stop()
            try:
                self.submit('test', Image.open(path).convert('RGB'))
            except Exception as exc:
                messagebox.showerror('画像', str(exc))

    def timed_read(self):
        """ALTキー検出に依存しない5秒後撮影。1フレームの結果は全て確認待ちにする。"""
        if not self.hwnd:
            self.status.set('撮影するゲームを選んでください。')
            return
        if not self.active_id or self.store.find(self.active_id)['status'] != 'waiting':
            self.status.set('先に「新しい周回」、または未取得の履歴を選んで「監視再開」を押してください。')
            return
        if self.busy:
            self.status.set('読取処理中です。下の監視表示で進行状況を確認してください。')
            return
        self.stop()
        token = self.epoch

        def countdown(left):
            if token != self.epoch:
                return
            if left:
                self.status.set(f'報酬読取まで {left}秒。ゲームへ戻ってALTを押し続けてください。')
                self.root.after(1000, lambda: countdown(left - 1))
            else:
                self.status.set('報酬を撮影・読取中です。')
                self.submit('manual')
        countdown(5)

    def show_test(self, result):
        text = '\n'.join((f"{KIND[r['kind']]}：{r['name']}" for r in result['labels']))
        messagebox.showinfo('画像確認（統計には記録しません）', text or result['message'])

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
        self.correct.set('')
        for i, row in enumerate(run['rows']):
            self.rows.insert('', 'end', iid=str(i), values=(row['name'], KIND[row['kind']]))

    def select_row(self, event=None):
        """元の切り抜きを整数倍率で表示し、細い漢字の線が補間でぼけるのを避ける。"""
        selected = self.rows.selection()
        if not selected or not self.display_id:
            return
        row = self.store.find(self.display_id)['rows'][int(selected[0])]
        self.correct.set(row['name'])
        image = Image.open(self.store.folder / row['image'])
        shown = ocr_image(image) if self.clean_preview.get() else image
        self.photo = ImageTk.PhotoImage(pixel_preview(shown))
        self.preview.configure(image=self.photo)

    def correct_row(self, kind):
        """選択行を修正して見本を学習する。他の過去周回は自動で変更しない。"""
        if self.busy:
            return
        selected = self.rows.selection()
        if not selected or not self.display_id:
            return
        try:
            run = self.store.find(self.display_id)
            row = run['rows'][int(selected[0])]
            name = self.correct.get().strip()
            self.vision.learn(name, kind, Image.open(self.store.folder / row['image']).convert('RGB'))
            row['name'] = name
            row['kind'] = kind
            run['status'] = 'review'
            self.store.save()
            self.refresh()
            self.select_run()
        except Exception as exc:
            messagebox.showerror('修正', str(exc))

    def confirm_run(self):
        if not self.display_id:
            return
        try:
            self.store.confirm(self.display_id)
            self.refresh()
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
