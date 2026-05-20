@echo off
echo ========================================
echo  Assistive Gaze Control - Integrated
echo ========================================
echo.
echo Starting eye tracking + web UI...
echo.
echo Mode: AUTO-CALIBRATION (default)
echo Calibration will start automatically
echo.
echo To disable auto-calibration, use:
echo   python web_ui_controller_integrated.py --no-demo
echo.

cd "eye tracker"
python web_ui_controller_integrated.py

pause
