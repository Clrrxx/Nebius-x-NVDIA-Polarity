@echo off
REM Phase 0: verify Nebius Token Factory + Nemotron capabilities (Windows).
REM Usage: scripts\verify_windows.bat [--record] [--skip-video] [--json]
setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"
set PYTHONIOENCODING=utf-8
if not exist "%ROOT%\.venv\Scripts\python.exe" (
  echo No .venv found. Run scripts\setup_windows.bat first.
  exit /b 1
)
"%ROOT%\.venv\Scripts\python.exe" -m polarity verify %*
exit /b %ERRORLEVEL%
