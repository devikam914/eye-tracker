@echo off
echo ========================================
echo  Assistive Gaze Control - Demo Mode
echo ========================================
echo.
echo Starting web UI in DEMO mode...
echo.
echo Mode: MANUAL CALIBRATION (demo=False)
echo Click 'Start Calibration' button to begin
echo.

cd "eye tracker"
python web_ui_controller_integrated.py --no-demo

pause
