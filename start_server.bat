@echo off
setlocal

cd /d "%~dp0"

:: 1. Detect Python binary (prefer venv)
if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON_BIN=%~dp0venv\Scripts\python.exe"
) else (
    set "PYTHON_BIN=python"
)

echo ================================================================
echo       Desktop Agent Server Launcher (Hands ^& Eyes Engine)
echo ================================================================
echo [OK] Using Python : %PYTHON_BIN%
echo [INFO] Endpoint   : http://127.0.0.1:8765
echo [INFO] Auth Token : %~dp0.agent_token
echo.
echo [INFO] Launching server... (Close window or press Ctrl+C to stop)
echo ================================================================
echo.

"%PYTHON_BIN%" agent_server.py %*
