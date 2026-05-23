@echo off
cd /d "%~dp0"
echo Starting Assistive Gaze Control (Quick Calibration - correction only)
echo.
call working-backend\.venv\Scripts\activate.bat
cd "eye tracker"
python app.py --quick-calib
if errorlevel 1 (
    echo.
    echo ERROR: See above. Run launch_integrated.bat first if no saved calibration exists.
)
pause
