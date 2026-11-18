@echo off
cd /d "%~dp0"
echo Onter platform: http://localhost:8770  (engine load takes about 5 seconds)
start "" /b cmd /c "timeout /t 8 /nobreak >nul & start http://localhost:8770"
python -u server/app.py --port 8770
pause
