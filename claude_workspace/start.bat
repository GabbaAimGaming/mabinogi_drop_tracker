@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "TCL_LIBRARY="
set "TK_LIBRARY="
set "PYTHONHOME="
set "PYTHONPATH="
py -3.12 -c "import sys,struct; assert struct.calcsize('P')==8" >nul 2>&1
if not errorlevel 1 (
  py -3.12 bootstrap.py 
  goto finish
)
python -c "import sys,struct; assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8" >nul 2>&1
if not errorlevel 1 (
  python bootstrap.py 
  goto finish
)
if exist ".venv-portable\Scripts\python.exe" (
  ".venv-portable\Scripts\python.exe" bootstrap.py 
  goto finish
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" bootstrap.py 
  goto finish
)
echo Python 3.12（64ビット）をインストールしてください。初回はtcl/tk機能も必要です。
pause
exit /b 1
:finish
if errorlevel 1 pause

