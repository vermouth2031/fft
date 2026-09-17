@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_network_validation.ps1"
if errorlevel 1 echo Tests stopped. Read the error above; do not treat this run as passed.
pause
