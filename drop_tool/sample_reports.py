"""提出用サンプルをローカル保存。通常の3周分画像整理とは独立し、自動送信しない。"""
from datetime import datetime
import json
from pathlib import Path
import platform
import threading
import uuid
from zipfile import ZipFile, ZIP_DEFLATED


class SampleReports:
    MAX_REPORTS = 100
    MAX_BYTES = 500_000_000

    def __init__(self, data_folder):
        self.folder = Path(data_folder) / '提出用サンプル'
        self.lock = threading.Lock()

    def save(self, kind, frames, metadata):
        """最大3枚の原寸画像と判定情報を1件として保存。上限時は削除せず告知する。"""
        with self.lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            completed = list(self.folder.glob('*/report.json'))
            size = sum(p.stat().st_size for p in self.folder.rglob('*') if p.is_file())
            if len(completed) >= self.MAX_REPORTS or size >= self.MAX_BYTES:
                raise OSError('提出用サンプルが上限（100件または500MB）に達しました。ZIP出力後にフォルダーを整理してください。')
            stamp = datetime.now().astimezone()
            name = stamp.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
            target = self.folder/name
            target.mkdir()
            selected = []
            if frames:
                for i in sorted({0, len(frames)//2, len(frames)-1}):
                    selected.append(frames[i])
            images = []
            for i, frame in enumerate(selected):
                filename = f'frame-{i:02}.png'
                frame.save(target/filename)
                images.append({'file':filename,'width':frame.width,'height':frame.height})
            report = dict(metadata)
            report.update(version=1, app_version='1.0', kind=kind,
                          created=stamp.isoformat(timespec='seconds'), images=images,
                          os=platform.platform())
            # レポートが完成するまでは提出ZIPの対象にしない。
            temp = target/'report.tmp'
            temp.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
            temp.replace(target/'report.json')
            return target

    def export(self, path):
        """完成済みサンプルだけZIP化。周回記録・設定ファイル一式は含めない。"""
        with self.lock:
            reports = sorted(self.folder.glob('*/report.json')) if self.folder.exists() else []
            if not reports:
                raise ValueError('提出用サンプルはまだありません。')
            with ZipFile(path,'w',ZIP_DEFLATED) as archive:
                for report in reports:
                    for file in sorted(report.parent.iterdir()):
                        if file.is_file() and file.suffix in ('.png','.json'):
                            archive.write(file,file.relative_to(self.folder).as_posix())
            return len(reports)
