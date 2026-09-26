@echo off
REM AntlantisAFK launcher - double-click to start the app.
cd /d "%~dp0"
py -3 main.py
if errorlevel 1 pause
