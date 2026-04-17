@echo off
REM Launch via pythonw.exe (no console). Uses PATH first, then fallback.
where pythonw.exe >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw.exe "%~dp0transscript.py"
) else (
    start "" "C:\Python312\pythonw.exe" "%~dp0transscript.py"
)
