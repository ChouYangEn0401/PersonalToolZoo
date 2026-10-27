@echo off
rem Run this tool from source with its own environment (logic in scripts\run.ps1).
rem Double-click to start it. From a terminal: run.bat [args for the tool]   or   run.bat --check
for %%I in ("%~dp0.") do set "TOOL=%%~nxI"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\scripts\run.ps1" %TOOL% %*
set RC=%ERRORLEVEL%
if not "%RC%"=="0" pause
exit /b %RC%
