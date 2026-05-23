@echo off
cd /d "%~dp0"
echo Starting Assistive Gaze Control (UI only - mouse mode)
echo Use mouse to navigate. Go to Settings to save family contact number.
echo.
call working-backend\.venv\Scripts\activate.bat
cd "eye tracker"
python app.py --no-calib
if errorlevel 1 (
    echo.
    echo ERROR: See above for details.
)
pause
