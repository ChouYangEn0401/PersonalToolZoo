@echo off
REM Launch the command panel directly (no packaging).
REM Paths are resolved from this file's own location, so CWD does not matter.
pushd "%~dp0"
"..\..\.venv\Scripts\python.exe" src\gui\command_panel.py
popd
