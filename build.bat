@echo off
rem Double-click: interactive menu. From a terminal: build.bat [args]  (same args as scripts\build.ps1)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build.ps1" %*
set RC=%ERRORLEVEL%
if "%~1"=="" pause
exit /b %RC%
