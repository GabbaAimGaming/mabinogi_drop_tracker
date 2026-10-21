"""操作画面の本体（起動・設定・監視ループ・読取結果の振り分け）。Tk更新はメインスレッドで行う。"""
import queue
import copy
import threading
import traceback
from types import MappingProxyType
import time
import sys
import tkinter as tk
from tkinter import messagebox
# [削減候補 2026-10-21] app.pyの分割で移動先（history_actions/manual_actions/sample_actions）へ。app.pyでは未使用。確認後に削除
# from tkinter import filedialog, ttk
# from PIL import Image, ImageTk
from .notification import CompletionSound
# [削減候補 2026-10-21] app.pyの分割で移動先（history_actions/manual_actions/sample_actions）へ。app.pyでは未使用。確認後に削除
# from .exporting import export_statistics
# from .image_display import pixel_preview
# from .label_images import ocr_image
from .reading import StableReading
from .tracker import Store, default_near, SHADOW_MISSIONS
from .vision import Vision
from . import read_worker
from . import windows_capture as capture
from . import settings as user_settings
from .reward_gate import RewardGate
from .chest_detector import ChestDetector
from .sample_reports import SampleReports
# [削減候補 2026-10-21] app.pyの分割で移動先（history_actions/manual_actions/sample_actions）へ。app.pyでは未使用。確認後に削除
# from .item_links import row_identity, name_key
# from .item_registration import assign
from . import manual_review
from .history_actions import HistoryActions
from .manual_actions import ManualActions
from .sample_actions import SampleActions
# [削減候補 2026-10-21] 表示名はhistory_actionsへ移動。app.pyでは未使用。確認後に削除
# STATUS = {'waiting': '未取得', 'review': '確認待ち', 'confirmed': '集計済み', 'discarded': '集計対象外'}
# KIND = {'material': '集計', 'excluded': '除外', 'review': '要確認'}

class App(HistoryActions, ManualActions, SampleActions):
    """Tkの操作画面。画像処理をワーカーへ渡し、結果はTk側で反映する。

    ここには起動・設定・監視ループ・読取結果の振り分け（handle_job）を置く。
    履歴操作はHistoryActions、手動撮影・周回内の修正はManualActions、
    提出用サンプルはSampleActionsにある（どれもAppの属性を前提にした混ぜ込み用クラス）。
    """

    # __init__を通さない検証用インスタンス（App.__new__）でも参照できる既定値。
    # どれも読むだけか、代入で差し替える値に限る。
    settings = MappingProxyType({})
    settings_views = None
    samples = None
    reward_gate = None
    chest_detector = None
    near_detector = None
    scan_trace = ()
    manual_target = None
    saved_read_target = None
    saved_read_expected = None

    def _build_widgets(self):
        """レイアウトを専用モジュールへ委譲し、読取の状態管理と分離する。"""
        from .ui import build_widgets
        build_widgets(self)

    def __init__(self, root, store=None):
        """記録・認識器と監視状態を初期化し、画面構築後にTkの定期処理を開始する。"""
        self.root = root
        root.title('カレンとドロップ記録 v1.1.8')
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
        from . import learning
        try:
            learning.maintain(self.store)
        except (OSError, ValueError) as exc:
            self.log_error(f'学習見本の整理を次回に延期しました：{exc}\n')
        manual_review.cleanup_confirmed(self.store)
        if not self.settings or not self.settings['evidence_auto_delete']:
            return 0
        from .retention import prune_evidence
        try:
            removed = prune_evidence(self.store, self.settings['evidence_keep_runs'])
        except (OSError, ValueError) as exc:
            self.log_error(f'証拠画像の整理に失敗しました：{exc}\n')
            return 0
        if removed:
            self.status.set(f'保存世代を超えた古い品名画像を{removed}枚整理しました（「設定」タブで変更できます）。')
            if self.settings_views:
                self.settings_views.refresh_usage()
        return removed

    def close(self):
        """更新準備中は待機し、それ以外は終了する。"""
        updates = getattr(self.settings_views, 'updates', None)
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
        return self.settings.get('scan_mode') == 'center'

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
            elif not self.settings.get('auto_reward', True):
                state = '監視：手動のみ。「3秒後に撮影」→「画像で確認・読取」を使ってください。'
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
        # 確認ダイアログ中は取得できない。探索で観測を遅らせず、記憶も更新しない。
        if near_dialog:
            return {'found':False,'match':None,'seconds':0.,'search':'blocked'}
        if (gate.previous is not None
                and 0<=now-gate.previous<=gate.max_gap
                and gate.has_chest_evidence(now)):
            return {'found':False,'match':None,'seconds':0.,'search':'recent'}
        if self.chest_detector is None:
            self.chest_detector=ChestDetector()
        return self.chest_detector.detect(frame)

    def submit(self, mode, image=None):
        """撮影と認識をワーカーで実行し、結果はpollで受け取る（read_worker）。

        epoch・対象ゲーム・対象周回は開始時点の値を渡し、古い結果の登録を防ぐ。
        """
        if self.busy:
            return
        self.busy = True
        self.worker_started = time.monotonic()
        self.worker_phase = '画面を撮影中'
        if mode in ('live', 'manual'):
            self.read_attempts += 1
        options = dict(epoch=self.epoch, hwnd=self.hwnd, manual_target=self.manual_target,
                       saved_target=self.saved_read_target,
                       saved_expected=copy.deepcopy(self.saved_read_expected),
                       center=mode == 'live' and image is None and self.center_scan())
        threading.Thread(target=read_worker.run, args=(self, mode, image),
                         kwargs=options, daemon=True).start()

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
                self.handle_job(*self.jobs.get_nowait())
        except queue.Empty:
            pass
        except Exception as exc:
            self.callback_error(type(exc), exc, exc.__traceback__)
        finally:
            self.root.after(150, self.poll)

    def handle_job(self, epoch, mode, result, error):
        if mode == 'start':
            # 途中経過。ワーカーは続いているのでbusyは解除しない。
            if epoch == self.epoch:
                self.show_progress(mode, result)
            return
        # 【様子見・削除予定】'captured'は本体のどこからも送られていない。
        # 実機で届かないことを確認したら、この見張りとshow_progressのコメントを消す。
        if mode == 'captured':
            self.log_error(f"想定外のcapturedイベントを受信しました：{result!r}\n")
            return
        if mode not in ('sample_saved', 'sample_error'):
            self.busy = False
        if epoch != self.epoch:
            return
        if error:
            if result and result.get('attempted'):
                self.read_failed(mode, result, error)
            else:
                self.status.set('読取できません：' + error)
                self.stable.reset()
            return
        handler = {'scan': self.show_scan, 'missed': self.save_missed,
                   'sample_saved': self.sample_saved, 'sample_error': self.sample_error,
                   'manual_photo': self.save_manual_photo, 'saved_read': self.apply_saved_read,
                   'test': self.show_test, 'manual': self.save_manual_reading}
        handler.get(mode, self.apply_live)(result)

    def show_progress(self, mode, result):
        self.completion_sound.play(kind='start')
        self.status.set('読取開始。ALTを押したまま、完了音までゲームを前面に置いてください。')
        # 【様子見・削除予定】'captured'の表示。送信元がないためコメントアウト中。
        # self.completion_sound.play(kind='captured')
        # self.status.set(f"撮影完了（{result['frames']}枚）。ALTを離して構いません。品名を解析しています…")

    def show_scan(self, result):
        self.status.set(result.get('message', '宝箱を探しています。') + f" ALT継続 {result.get('elapsed', 0):.1f}/3秒")

    def apply_live(self, result):
        # 撮影中の画面切替も再確認し、別ウィンドウへ移った結果を採用しない。
        if not self.watching or not self.ready(self.hwnd):
            self.stable.reset()
            self.reset_reward()
            return
        labels = result.get('labels')
        if result.get('final'):
            # 表示中に連写したフレームの多数決で確定済み。
            self.stable.reset()
            if labels:
                self.save_live_reading(result)
            else:
                self.read_failed('auto', result, result['message'])
            return
        if not labels:
            # ALTを離して品名板が消えた。直前に同じ一覧を2回以上読めていれば採用する。
            # 録画ではALT表示は約1.4秒で、3回一致を待つと間に合わないことがある。
            held = self.stable.release()
            if held is not None:
                self.save_live_reading(held)
            else:
                self.status.set(result['message'])
            return
        if self.stable.observe(result):
            self.save_live_reading(self.stable.finish())
        else:
            self.status.set(result['message'] + ' / 同じ品名表示を確認中。')
            # ALT表示が見えている間は待たずに続けて読む（表示は数秒で消えるため）。
            self.submit('live')

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

    def reset_reward(self):
        """周回・撮影対象・監視状態が変わった時は、箱の記憶と3秒待ちを消す。"""
        if self.reward_gate is not None:
            self.reward_gate.reset()
        self.scan_trace = []

    def change_auto_reward(self, enabled):
        if self.save_setting(auto_reward=bool(enabled)):
            self.epoch += 1
            self.stable.reset()
            self.reset_reward()
            self.status.set('自動読取は試験機能です。手動読取はいつでも使えます。')

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
