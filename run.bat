@echo off
setlocal

echo ============================================================
echo Assignment 1 - Histogram Experiment
echo ============================================================
echo.

cd /d "%~dp0"

if not exist results mkdir results

echo [1/2] Generating PostgreSQL histograms...
python code\q1_plots.py

if errorlevel 1 (
    echo.
    echo ERROR: q1_plots.py failed.
    pause
    exit /b 1
)

echo.
echo [2/2] Running serial histogram experiment...
python code\histogram.py

if errorlevel 1 (
    echo.
    echo ERROR: histogram.py failed.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo SUCCESS
echo ============================================================
echo All experiments have completed successfully.
echo.
echo Generated files are available in:
echo %cd%\results
echo.

pause
endlocal