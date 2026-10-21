@echo off
REM Start Polarity and open the browser (Windows). Extra arguments are passed to `polarity run`.
setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"
set PYTHONIOENCODING=utf-8
if not exist "%ROOT%\.venv\Scripts\python.exe" (
  echo No .venv found. Run scripts\setup_windows.bat first.
  exit /b 1
)
"%ROOT%\.venv\Scripts\python.exe" -m polarity run --open-browser %*
exit /b %ERRORLEVEL%
