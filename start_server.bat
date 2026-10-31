@echo off
setlocal
cd /d "%~dp0"

powershell.exe -ExecutionPolicy Bypass -NoProfile -File "%~dp0start_server.ps1" %*
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Server launcher exited with code %ERRORLEVEL%.
    pause
)
