@echo off
rem Double-click: interactive menu. From a terminal: release.bat [args]  (same args as scripts\release.ps1)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\release.ps1" %*
set RC=%ERRORLEVEL%
if "%~1"=="" pause
exit /b %RC%
