@echo off
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "%~dp0stop_server.ps1" %*
