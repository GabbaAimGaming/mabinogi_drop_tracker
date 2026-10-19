"""監視と履歴操作を調整する。Tk更新はメインスレッドで行う。"""
import queue
import threading
import traceback
import time
import sys
import tkinter as tk
from tkinter import messagebox, filedialog
from PIL import Image, ImageTk
from .notification import CompletionSound
from .exporting import export_statistics
from .image_display import pixel_preview
from .label_images import ocr_image
from .tracker import ROOT, Store, StableReading, default_near, SHADOW_MISSIONS
from .vision import Vision, CENTER
from .alt_display import quick_check
from . import alt_capture
from . import windows_capture as capture
from . import settings as user_settings
from .reward_gate import RewardGate
from .chest_detector import ChestDetector
from .near_dialog import NearDialogDetector
from .sample_reports import SampleReports
from .item_links import row_identity, name_key
from .item_registration import assign
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
        root.title('カレンとドロップ記録 v1.1.2.1（次版検証用）')
        root.geometry('1020x760')
        root.minsize(780, 600)
        from .theme import apply_theme
        apply_theme(root)
        self.store = store or Store()
        self.completion_sound = CompletionSound(self.store.folder)
        self.sound_enabled = tk.BooleanVar(value=self.completion_sound.enabled)
        self.vision = Vision(self.store)
        self.settings = user_settings.load(self.store.folder)
        self.reward_gate = RewardGate()
        self.chest_detector = None
        self.near_detector = None
        self.samples = SampleReports(self.store.folder)
        self.scan_trace = []
        self.scan_mode = tk.StringVar(value=self.settings['scan_mode'])
        self.stable = StableReading()
        root.report_callback_exception = self.callback_error
        self.active_id = None
        self.hwnd = None
        self.busy = False
        self.watching = False
        self.jobs = queue.Queue()
        # 停止・周回変更・ゲーム変更で増やし、以前のワーカー結果を無効にする。
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
        root.protocol('WM_DELETE_WINDOW', self.close)
        # 起動直後の画面表示を遅らせないよう、古い画像の整理は少し後に行う。
        root.after(2000, self.prune_evidence)
        # 表示後に通信ワーカーを起動。自己診断と開発時は外部通信しない。
        if getattr(sys, 'frozen', False) and '--self-test' not in sys.argv:
            root.after(1500, self.settings_views.updates.startup_check)

    def prune_evidence(self):
        """設定に従い、テキスト化・バックアップ済みの古い証拠画像を削除する。"""
        if not getattr(self, 'settings', None) or not self.settings['evidence_auto_delete']:
            return 0
        from .retention import prune_evidence
        try:
            removed = prune_evidence(self.store, self.settings['evidence_keep_runs'])
        except (OSError, ValueError) as exc:
            self.log_error(f'証拠画像の整理に失敗しました：{exc}\n')
            return 0
        if removed:
            self.status.set(f'保存世代を超えた古い品名画像を{removed}枚整理しました（「設定」タブで変更できます）。')
            if hasattr(self, 'settings_views'):
                self.settings_views.refresh_usage()
        return removed

    def close(self):
        """更新準備中は待機し、それ以外は終了する。"""
        updates = getattr(getattr(self, 'settings_views', None), 'updates', None)
        if updates and updates.installing:
            messagebox.showinfo('更新中', '更新準備が終わるまでお待ちください。')
            return
        self.root.destroy()

    # ---- 設定と前面撮影 ----

    def save_setting(self, **changes):
        try:
            self.settings = user_settings.save(self.store.folder, **changes)
            return True
        except (OSError, ValueError) as exc:
            messagebox.showerror('設定を保存できません', str(exc))
            return False

    def ready(self, hwnd):
        """選択ゲームが前面にあり、最小化されていない場合だけ撮影する。"""
        return capture.active(hwnd)

    def grab(self, hwnd, region=None):
        """前面のゲーム画面を撮影する。"""
        return capture.capture(hwnd, region) if region is not None else capture.capture(hwnd)

    def center_scan(self):
        return getattr(self, 'settings', {}).get('scan_mode') == 'center'

    def change_scan_mode(self):
        if not self.save_setting(scan_mode=self.scan_mode.get()):
            self.scan_mode.set(self.settings['scan_mode'])
            return
        self.epoch += 1
        self.stable.reset()
        self.reset_reward()

    def preview_sounds(self):
        """開始・完了・エラーの順に鳴らして、実際の通知を確認する。"""
        self.completion_sound.play(preview=True, kind='start')
        self.root.after(600, lambda: self.completion_sound.play(preview=True))
        self.root.after(1800, lambda: self.completion_sound.play(preview=True, kind='error'))

    def change_sound(self):
        try:
            self.completion_sound.set_enabled(self.sound_enabled.get())
        except OSError as exc:
            self.sound_enabled.set(self.completion_sound.enabled)
            messagebox.showerror('音の設定を保存できません', str(exc))

    def context_changed(self, event=None):
        if self.dungeon.get() != self.last_context[0] and self.dungeon.get() in SHADOW_MISSIONS:
            self.difficulty.set('エリート')
        context = (self.dungeon.get(), self.difficulty.get())
        if context != self.last_context:
            self.near.set(default_near(*context))
            self.last_context = context

    def callback_error(self, kind, error, tb):
        detail = ''.join(traceback.format_exception(kind, error, tb))
        self.log_error(detail + '\n')
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
            self.reset_reward()
    
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
            self.reset_reward()
            self.watching = True
            self.status.set('監視中。クリア後、自分の宝箱を開け、拾う前にALTを押したまま待ってください。')
            self.refresh()
        except Exception as exc:
            messagebox.showerror('開始できません', str(exc))

    def stop(self):
        self.watching = False
        self.epoch += 1
        self.stable.reset()
        self.reset_reward()
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
        self.reset_reward()
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
            elif not self.ready(self.hwnd):
                state = '監視：ゲームが手前になるのを待っています。'
                self.stable.reset()
                self.reset_reward()
            elif not getattr(self, 'settings', {}).get('auto_reward', True):
                state = '監視：手動読取のみ。5秒後の報酬読取を使ってください。'
            elif self.center_scan():
                state = '監視：中央のALT品名表示を待っています（キー入力は読みません）。'
                self.submit('live')
            else:
                state = '監視：画面の品名表示を探しています（ALTキー検出不要）。'
                self.submit('live')
            self.set_diagnostic(state)
        except Exception as exc:
            self.stable.reset()
            self.status.set('読取エラー：' + str(exc))
        finally:
            # 中央スキャンは軽い判定だけで済むため、表示への反応を早くする。
            self.root.after(350 if self.center_scan() else 700, self.tick)

    def set_diagnostic(self, text):
        self.diagnostic.set(text + f' / 読取開始 {self.read_attempts}回')
        key = text.split('（')[0]
        if key == self.last_diagnostic:
            return
        self.last_diagnostic = key
        from .retention import append_log
        append_log(self.store.folder / 'monitor.log', time.strftime('%H:%M:%S ') + text + '\n', limit=200000)

    def reward_detection(self, frame, near_dialog, now):
        """Keep checking ALT while the already-confirmed chest memory is valid."""
        gate=self.reward_gate
        if (not near_dialog and gate.previous is not None
                and 0<=now-gate.previous<=gate.max_gap and now<=gate.chest_until
                and gate.chest_until>0):
            return {'found':False,'match':None,'seconds':0.,'search':'recent'}
        if self.chest_detector is None:
            self.chest_detector=ChestDetector()
        return self.chest_detector.detect(frame)

    def submit(self, mode, image=None):
        """撮影と認識をワーカーで実行し、結果をpollへ返す。

        liveは宝箱と3秒のALT表示が揃ってから連写し、候補を多数決でまとめる。
        manualは5秒後の1枚を登録候補にする。missedは提出画像のみ、testは表示のみ。
        epochは開始時点を固定し、古い結果の登録を防ぐ。
        """
        if self.busy:
            return
        self.busy = True
        epoch = self.epoch
        hwnd = self.hwnd
        self.worker_started = time.monotonic()
        self.worker_phase = '画面を撮影中'
        if mode in ('live', 'manual'):
            self.read_attempts += 1

        # ALTキーの状態はゲームが他アプリへ渡さないため、画面の表示で判断する。
        # 箱の探索には全体画像が必要。中央設定は品名の解析範囲だけを変える。
        center = mode == 'live' and image is None and self.center_scan()
        burst = mode == 'live' and image is None
        region = None  # 箱は中央外にもあるため常にゲームの画面全体を撮影する。

        def middle(frame):
            w, h = frame.size
            return frame.crop((round(w * CENTER[0]), round(h * CENTER[1]),
                               round(w * CENTER[2]), round(h * CENTER[3])))

        def again():
            if self.epoch != epoch:
                raise ValueError('監視が停止・変更されました。')
            return self.grab(hwnd, region)

        def work():
            frame = None
            frames = []
            attempted = mode == 'manual'
            try:
                frame = image if image is not None else self.grab(hwnd)
                if mode == 'missed':
                    self.jobs.put((epoch, mode, {'frame':frame}, None))
                    return
                if mode == 'manual':
                    self.jobs.put((epoch, 'start', {'manual':True}, None))
                    self.save_capture(frame)
                if burst:
                    if getattr(self, 'near_detector', None) is None:
                        self.near_detector = NearDialogDetector()
                    near_dialog = self.near_detector.detect(frame)
                    detection = self.reward_detection(frame,near_dialog,time.monotonic())
                    alt = not near_dialog and quick_check(middle(frame))
                    if self.epoch != epoch:
                        self.jobs.put((epoch, 'scan', {}, None))
                        return
                    now = time.monotonic()
                    triggered = self.reward_gate.observe(detection['found'], alt, now, blocked=near_dialog)
                    scan = dict(detection, alt=bool(alt), near_dialog=near_dialog, elapsed=self.reward_gate.elapsed(now))
                    self.scan_trace = (self.scan_trace + [dict(scan,time=now)])[-30:]
                    if not triggered:
                        message = ('宝箱を確認。ALT表示を3秒待っています。' if now <= self.reward_gate.chest_until
                                   else '宝箱を探しています。未検出の場合は手動読取を使ってください。')
                        if near_dialog:
                            message = 'ネアル確認画面のため待機中。閉じてからALT表示を3秒確認します。'
                        self.jobs.put((epoch, 'scan', dict(scan,message=message), None))
                        return
                    attempted = True
                    self.jobs.put((epoch, 'start', {'manual':False}, None))
                    self.worker_phase = '取得条件成立・報酬を連写中'
                    frames = alt_capture.collect(again, lambda f: not self.near_detector.detect(f) and quick_check(middle(f)), first=frame)
                    self.worker_phase = f'撮影済み（{len(frames)}枚）・品名を解析中'
                    if len(frames) < 2:
                        result = {'labels':[], 'message':'品名表示中の画像が2枚以上集まりませんでした。'}
                    else:
                        result = alt_capture.read(lambda f: self.vision.analyze(middle(f),cropped=True)
                                                  if center else self.vision.analyze(f), frames)
                    result.update(final=True, attempted=True, sample_frames=frames,
                                  detection=scan, frame=frames[len(frames)//2])
                    self.jobs.put((epoch, mode, result, None))
                    return
                self.worker_phase = '品名を解析中'
                result = self.vision.analyze(frame)
                if mode in ('live','manual'):
                    result.update(frame=frame, sample_frames=[frame], attempted=True)
                self.jobs.put((epoch, mode, result, None))
            except Exception as exc:
                self.jobs.put((epoch, mode, {'sample_frames':frames or ([frame] if frame is not None else []),
                                            'attempted':attempted}, str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def save_capture(self, frame):
        """確認用の元スクリーンショット。一時ファイル経由で上書きし、失敗は記録だけ残す。"""
        target = self.store.folder / 'last-loot-capture.png'
        import uuid
        temporary = target.with_name('last-loot-capture.' + uuid.uuid4().hex + '.tmp.png')
        try:
            frame.save(temporary)
            temporary.replace(target)
        except OSError as exc:
            self.log_error(f'元スクリーンショットを保存できません：{exc}\n')

    def log_error(self, text):
        from .retention import append_log
        append_log(self.store.folder / 'errors.log', text)

    def poll(self):
        """結果の世代番号を照合し、停止や周回変更前の結果を破棄する。"""
        try:
            while True:
                epoch, mode, result, error = self.jobs.get_nowait()
                if mode == 'start':
                    if epoch == self.epoch:
                        self.completion_sound.play(kind='start')
                        self.status.set('読取開始。ALTを押したまま、完了音までゲームを前面に置いてください。')
                    continue
                if mode == 'captured':
                    # 撮影だけ終わった途中経過。ワーカーは解析中なのでbusyは解除しない。
                    if epoch == self.epoch:
                        self.completion_sound.play(kind='captured')
                        self.status.set(f"撮影完了（{result['frames']}枚）。ALTを離して構いません。品名を解析しています…")
                    continue
                if mode not in ('sample_saved','sample_error'):
                    self.busy = False
                if epoch != self.epoch:
                    continue
                if error:
                    if result and result.get('attempted'):
                        self.read_failed(mode, result, error)
                    else:
                        self.status.set('読取できません：' + error)
                        self.stable.reset()
                    continue
                if mode == 'scan':
                    self.status.set(result.get('message','宝箱を探しています。') + f" ALT継続 {result.get('elapsed',0):.1f}/3秒")
                    continue
                if mode == 'missed':
                    self.submit_sample('missed_detection', [result['frame']], {'reason':'利用者が自動で読めなかったと報告。ALT表示は不要。'})
                    continue
                if mode == 'sample_saved':
                    prefix = ('読み取れませんでした。手動読取に切り替えてください。' if result.get('kind','').endswith('_failure')
                              else '読取完了。履歴で確認してください。' if result.get('kind','').endswith('_success') else '')
                    self.status.set(prefix + ' 提出用サンプルを保存しました：' + result['path'])
                    continue
                if mode == 'sample_error':
                    prefix = '読み取れませんでした。手動読取に切り替えてください。' if result.get('kind','').endswith('_failure') else ''
                    self.status.set(prefix + ' 提出用サンプルを保存できません：' + result['reason'])
                    continue
                if mode == 'test':
                    self.show_test(result)
                elif mode == 'manual':
                    if not result.get('labels'):
                        self.read_failed('manual', result, result['message'])
                    else:
                        rows = self.store.persist_rows(self.active_id, result['labels'])
                        self.store.record(self.active_id, rows, require_review=True)
                        self.refresh()
                        self.status.set('撮影・読取できました。履歴タブで品名と除外対象を確認し、この周回を確定してください。')
                        self.completion_sound.play()
                        self.notify_unregistered(result)
                        self.submit_sample('manual_success', result.get('sample_frames',[]), self.read_metadata(result))
                else:
                    # 撮影中の画面切替も再確認し、別ウィンドウへ移った結果を採用しない。
                    if not self.watching or not self.ready(self.hwnd):
                        self.stable.reset()
                        self.reset_reward()
                        continue
                    labels = result.get('labels')
                    if result.get('final'):
                        # 表示中に連写したフレームの多数決で確定済み。
                        self.stable.reset()
                        if labels:
                            self.save_live_reading(result)
                        else:
                            self.read_failed('auto', result, result['message'])
                        continue
                    if not labels:
                        # ALTを離して品名板が消えた。直前に同じ一覧を2回以上読めていれば採用する。
                        # 録画ではALT表示は約1.4秒で、3回一致を待つと間に合わないことがある。
                        held = self.stable.release()
                        if held is not None:
                            self.save_live_reading(held)
                        else:
                            self.status.set(result['message'])
                        continue
                    if self.stable.observe(result):
                        self.save_live_reading(self.stable.finish())
                    else:
                        self.status.set(result['message'] + ' / 同じ品名表示を確認中。')
                        # ALT表示が見えている間は待たずに続けて読む（表示は数秒で消えるため）。
                        self.submit('live')
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
        frame = result.pop('frame', None)
        if frame is not None:
            # PNG圧縮は画面を止めないよう別スレッドで1回だけ行う。
            threading.Thread(target=self.save_capture, args=(frame,), daemon=True).start()
        self.watching = False
        self.refresh()
        self.status.set('読取完了。ALTを離して構いません。履歴で宝箱の報酬か確認し、周回を確定してください。')
        self.completion_sound.play()
        self.notify_unregistered(result)
        self.submit_sample('auto_success', result.get('sample_frames',[]), self.read_metadata(result))

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
        """ALTキー検出に依存しない5秒後撮影。1フレームの周回は確認待ちにし、登録名の設定は保持する。"""
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

    def reset_reward(self):
        """周回・撮影対象・監視状態が変わった時は、箱の記憶と3秒待ちを消す。"""
        gate = getattr(self, 'reward_gate', None)
        if gate is not None:
            gate.reset()
        self.scan_trace = []

    def change_auto_reward(self, enabled):
        if self.save_setting(auto_reward=bool(enabled)):
            self.epoch += 1
            self.stable.reset()
            self.reset_reward()
            self.status.set('自動読取は試験機能です。手動読取はいつでも使えます。')

    def read_metadata(self, result):
        return {'reason':result.get('message',''), 'detection':result.get('detection'),
                'capture_count':result.get('frames'), 'frame_analysis':result.get('frame_analysis',[]),
                'rows':[{'name':r['name'],'raw':r.get('raw',''),'kind':r['kind'],
                         'registered':r.get('registered'),'pos':r.get('pos')} for r in result.get('labels',[])]}

    def sample_context(self):
        """提出に必要な設定と判定ログだけ。records.json一式は含めない。"""
        run = None
        if self.active_id:
            try:
                source = self.store.find(self.active_id)
                run = {key:source.get(key) for key in ('id','dungeon','difficulty','near','status')}
            except StopIteration:
                pass
        return {'player_name':self.store.player_name,'run':run,
                'settings':dict(getattr(self,'settings',{})),
                'scan_trace':list(getattr(self,'scan_trace',[]))}

    def submit_sample(self, kind, frames, metadata):
        """PNG保存を別スレッドへ渡す。提出画像の保存失敗で周回記録を取り消さない。"""
        reports = getattr(self, 'samples', None)
        if reports is None:  # 初期化前の検証用Appには提出機能がない。
            return
        context = self.sample_context()
        context.update(metadata)
        token = self.epoch
        def save():
            try:
                path = reports.save(kind, frames, context)
                self.jobs.put((token,'sample_saved',{'path':str(path),'kind':kind},None))
            except Exception as exc:
                self.jobs.put((token,'sample_error',{'reason':str(exc),'kind':kind},None))
        threading.Thread(target=save,daemon=True).start()

    def read_failed(self, mode, result, reason):
        """開始した読取の失敗だけ通知。箱を未検出の間は勝手に失敗扱いにしない。"""
        self.watching = False
        self.stable.reset()
        self.completion_sound.play(kind='error')
        self.status.set('読み取れませんでした。手動読取に切り替えてください。理由：' + reason)
        metadata = self.read_metadata(result)
        metadata['reason'] = reason
        self.submit_sample(mode+'_failure', result.get('sample_frames',[]), metadata)
        self.reset_reward()

    def report_missed(self):
        """5秒後にゲーム画面とログだけ保存。OCR・周回登録をしない。"""
        if self.busy:
            self.status.set('読取処理が終わってから押してください。')
            return
        if not self.hwnd:
            self.status.set('撮影するゲームを選んでください。')
            return
        trace = list(self.scan_trace)
        self.stop()
        self.scan_trace = trace
        token = self.epoch
        def countdown(left):
            if token != self.epoch:
                return
            if left:
                self.status.set(f'検証用撮影まで{left}秒。ゲームへ戻り、宝箱を画面に入れてください。ALTは不要です。')
                self.root.after(1000,lambda:countdown(left-1))
            else:
                self.submit('missed')
        countdown(5)

    def export_samples(self):
        """利用者が内容を確認して提出するためのZIP。ネット送信は行わない。"""
        path = filedialog.asksaveasfilename(defaultextension='.zip',initialfile='KarenDrop-samples.zip')
        if not path:
            return
        try:
            count = self.samples.export(path)
            self.status.set(f'{count}件の提出用サンプルをZIPにまとめました。画像とプレイヤー名を確認してから渡してください。')
        except (ValueError,OSError) as exc:
            messagebox.showerror('サンプルZIP',str(exc))
