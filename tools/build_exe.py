"""Windows配布用EXEを再現する開発用スクリプト。利用者のPCでは実行不要。"""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    # 実行環境と資産を1フォルダーへまとめる。dataは一切コピーしない。
    output = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'dist'
    work = ROOT / 'build'
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--windowed', '--onedir',
               '--name', 'KarenDrop', '--distpath', str(output), '--workpath', str(work),
               '--specpath', str(work), '--copy-metadata', 'Pillow', '--copy-metadata', 'numpy',
               '--copy-metadata', 'opencv-python', '--copy-metadata', 'onnxruntime',
               '--copy-metadata', 'windows-capture', '--collect-binaries', 'windows_capture']
    for excluded in ('rapidocr_onnxruntime', 'matplotlib', 'pandas', 'scipy'):
        command.extend(['--exclude-module', excluded])
    command.append(str(ROOT / 'app.py'))
    subprocess.run(command, cwd=ROOT, check=True)
    target = output / 'KarenDrop'
    for name in ('assets', 'references', 'dictionary-docs', 'models', 'licenses'):
        shutil.copytree(ROOT / name, target / name, dirs_exist_ok=True)
    # windows-capture（MIT）のライセンスを、導入済みパッケージから同梱する。
    from importlib.metadata import distribution
    for file in distribution('windows-capture').files or []:
        if 'license' in file.name.lower():
            shutil.copy2(file.locate(), target / 'licenses' / ('windows-capture-' + file.name))
    for name in ('item-master.json', 'exclusions.json', 'requirements.txt', 'README_EXE.txt', '更新内容.txt', '更新方法.txt', '現在の問題点と対処方法.txt', 'update_helper.ps1', 'update-source.json'):
        shutil.copy2(ROOT / name, target / name)
    for name in ('配布者向け更新手順.txt', '更新情報-初期登録用.json'):
        shutil.copy2(ROOT / name, target / name)
    print('配布フォルダー：', target)


if __name__ == '__main__':
    main()
