@echo off
REM One-time setup for Windows (runs setup_windows.ps1 without changing your execution policy).
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1" %*
exit /b %ERRORLEVEL%
