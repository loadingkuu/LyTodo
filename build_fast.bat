@echo off
chcp 65001 >nul
setlocal

REM 永远切到 bat 所在目录（关键）
cd /d "%~dp0"

title LyTodo Build
echo ================================
echo        LyTodo 打包开始
echo ================================
echo.

echo [1/4] Python:
python --version
echo.

echo [2/4] 检查图标文件:
if not exist "assets\app.ico" (
  echo ERROR: 找不到 assets\app.ico
  pause
  exit /b 1
)
for %%I in ("assets\app.ico") do echo icon=%%~fI  size=%%~zI bytes
echo.

echo [3/4] 清理旧输出:
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q *.spec 2>nul
echo.

echo [4/4] 开始 PyInstaller:
python -m PyInstaller ^
  --noconsole ^
  --onedir ^
  --name LyTodo ^
  --icon="assets\app.ico" ^
  --clean ^
  --collect-all requests ^
  --collect-all certifi ^
  app.py

echo.
echo ================================
echo 打包完成：dist\LyTodo\LyTodo.exe
echo ================================
pause