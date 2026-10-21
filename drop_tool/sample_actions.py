"""提出用サンプル（Appへ混ぜて使う）。

読取の成功・失敗時のサンプル保存（別スレッド）、「読めなかった」報告の撮影、
提出用ZIPの書き出しを担当する。ネットへの送信は行わない。
"""
import threading
from tkinter import messagebox, filedialog
from . import manual_review


class SampleActions:
    """Appの提出用サンプル操作。Appの属性（samples、jobs、epoch等）を前提にする。"""

    def save_missed(self, result):
        self.submit_sample('missed_detection', [result['frame']], {'reason': '利用者が自動で読めなかったと報告。ALT表示は不要。'})

    def sample_saved(self, result):
        manual_review.cleanup_confirmed(self.store)
        kind = result.get('kind', '')
        prefix = ('読み取れませんでした。手動読取に切り替えてください。' if kind.endswith('_failure')
                  else '読取完了。履歴で確認してください。' if kind.endswith('_success') else '')
        self.status.set(prefix + ' 提出用サンプルを保存しました：' + result['path'])

    def sample_error(self, result):
        prefix = '読み取れませんでした。手動読取に切り替えてください。' if result.get('kind', '').endswith('_failure') else ''
        self.status.set(prefix + ' 提出用サンプルを保存できません：' + result['reason'])

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
                'settings':dict(self.settings),
                'scan_trace':list(self.scan_trace)}

    def submit_sample(self, kind, frames, metadata):
        """PNG保存を別スレッドへ渡す。提出画像の保存失敗で周回記録を取り消さない。"""
        reports = self.samples
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

    def report_missed(self):
        """3秒後に提出用のゲーム画面とログだけ保存。OCR・周回登録をしない。"""
        if self.busy:
            self.status.set('読取処理が終わってから押してください。')
            return
        if not self.hwnd:
            self.status.set('撮影するゲームを選んでください。')
            return
        trace = list(self.scan_trace)
        self.stop()
        self.scan_trace = trace
        self.countdown(3, '検証用撮影まで{left}秒。ゲームへ戻り、宝箱を画面に入れてください。ALTは不要です。', 'missed')

        # [削減候補 2026-10-21] self.countdownへ集約した旧実装。確認後に削除
        # token = self.epoch
        # def countdown(left):
        #     if token != self.epoch:
        #         return
        #     if left:
        #         self.status.set(f'検証用撮影まで{left}秒。ゲームへ戻り、宝箱を画面に入れてください。ALTは不要です。')
        #         self.root.after(1000,lambda:countdown(left-1))
        #     else:
        #         self.submit('missed')
        # countdown(3)

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
