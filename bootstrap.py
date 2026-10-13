"""配布用の起動準備。Codexのキャッシュや利用者名に依存しない。"""
import os
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def clean_environment():
    """別Python用のTcl設定とモジュール探索先を子プロセスへ持ち込まない。"""
    env = os.environ.copy()
    for name in ('TCL_LIBRARY', 'TK_LIBRARY', 'PYTHONHOME', 'PYTHONPATH'):
        env.pop(name, None)
    env['PYTHONIOENCODING'] = 'utf-8'
    return env


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, env=clean_environment(), **kwargs)


def healthy_python(path):
    """他PCからコピーされた環境は実行して確認する。存在だけでは採用しない。"""
    if not Path(path).is_file():
        return False
    code = ('import sys,struct,tkinter as t; '
            'assert sys.version_info[:2]==(3,12) and struct.calcsize("P")==8; '
            'r=t.Tk();r.withdraw();r.destroy()')
    try:
        return run([str(path), '-c', code], stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def requirements_match(python):
    """importの成功だけで省略せず、配布版が指定する直接依存の版を確認する。"""
    code = ('from importlib.metadata import version; from pathlib import Path; '
            'pairs=[s.strip().split("==") for s in Path("requirements.txt").read_text().splitlines() '
            'if s.strip() and not s.startswith("#")]; '
            'assert all(version(n)==v for n,v in pairs); import PIL,cv2,numpy')
    return run([str(python), '-c', code], stdout=subprocess.PIPE,
               stderr=subprocess.PIPE).returncode == 0


def main():
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 12) or struct.calcsize('P') != 8:
        print('Windows用Python 3.12（64ビット）が必要です。')
        return 1
    if '--diagnose' in sys.argv:
        # 診断だけの場合はインストールや環境作成をしない。
        candidates = [ROOT / '.venv-portable/Scripts/python.exe', ROOT / '.venv/Scripts/python.exe']
        python = next((p for p in candidates if healthy_python(p)), Path(sys.executable))
        return run([str(python), '-m', 'drop_tool.preflight']).returncode
    candidates = [ROOT / '.venv-portable/Scripts/python.exe', ROOT / '.venv/Scripts/python.exe']
    python = next((p for p in candidates if healthy_python(p)), None)
    if python is None:
        target = ROOT / '.venv-portable'
        if target.exists():
            print('.venv-portableを実行できません。診断.batを実行してください。既存フォルダーは削除していません。')
            return 1
        if not healthy_python(sys.executable):
            print('Pythonの画面機能（Tk）を使えません。Python 3.12のtcl/tk機能を確認してください。')
            return 1
        print('このPC用の実行環境を準備します。既存の記録には触れません。')
        if run([sys.executable, '-m', 'venv', str(target)]).returncode:
            return 1
        python = target / 'Scripts/python.exe'
    if not requirements_match(python):
        print('指定された依存ライブラリを準備します（ネット接続が必要です）。')
        if run([str(python), '-m', 'pip', 'install', '-r', 'requirements.txt']).returncode:
            print('依存ライブラリの準備に失敗しました。上のエラーを確認してください。')
            return 1
    if run([str(python), '-m', 'drop_tool.preflight']).returncode:
        print('起動前の確認で問題が見つかりました。環境診断.txtを確認してください。')
        return 1
    return run([str(python), 'app.py']).returncode


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, subprocess.SubprocessError) as exc:
        print('起動準備に失敗しました：', exc)
        sys.exit(1)
