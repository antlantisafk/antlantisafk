@echo off
REM Build AntlantisAFK.exe with PyInstaller.
REM Prereqs: py -3 -m pip install -r requirements-dev.txt
cd /d "%~dp0"
py -3 build.py %*
