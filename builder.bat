@echo off
REM Simple builder: run PyInstaller with the project spec
.venv\Scripts\python.exe -m PyInstaller GUI__Encrypter.spec
EXIT /B %ERRORLEVEL%