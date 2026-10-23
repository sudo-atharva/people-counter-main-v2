@echo off
setlocal
cd /d "%~dp0"

if not exist app.pid (
    echo People Counter is not running.
    timeout /t 3 >nul
    exit /b 0
)
set /p PID=<app.pid

rem Ask the window to close first so the app can shut down cleanly.
taskkill /PID %PID% >nul 2>nul
timeout /t 3 /nobreak >nul
tasklist /FI "PID eq %PID%" | find "%PID%" >nul && taskkill /PID %PID% /T /F >nul 2>nul

rem Close the minimized console window that run.bat opened.
taskkill /FI "WINDOWTITLE eq People Counter (console)*" /T /F >nul 2>nul
if exist app.pid del app.pid
echo People Counter stopped.
timeout /t 2 >nul
