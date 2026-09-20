@echo off
setlocal
if defined IQ_PYTHON (
  "%IQ_PYTHON%" "%~dp0host\monitor.py"
) else if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%~dp0host\monitor.py"
) else (
  python "%~dp0host\monitor.py"
)
if errorlevel 1 pause
