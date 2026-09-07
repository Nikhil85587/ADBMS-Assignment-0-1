```bat
@echo off
setlocal EnableExtensions

echo ============================================================
echo ADBMS Assignment 1 - Complete Histogram Experiment
echo ============================================================
echo.

cd /d "%~dp0"

if not exist results mkdir results

REM ------------------------------------------------------------
REM Check that Python is available
REM ------------------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found.
    echo Please install Python 3.x and add it to PATH.
    pause
    exit /b 1
)

echo Python:
python --version
echo.

REM ------------------------------------------------------------
REM Step 1: PostgreSQL built-in histogram investigation
REM ------------------------------------------------------------
echo [1/4] Generating PostgreSQL histograms from pg_stats...
python code\q1_plots.py

if errorlevel 1 (
    echo.
    echo ERROR: q1_plots.py failed.
    echo Check PostgreSQL configuration and database connectivity.
    pause
    exit /b 1
)

echo.
echo [1/4] Completed successfully.
echo.

REM ------------------------------------------------------------
REM Step 2: Main optimal serial histogram experiment
REM ------------------------------------------------------------
echo [2/4] Running optimal serial histogram experiment...
python code\histogram.py

if errorlevel 1 (
    echo.
    echo ERROR: histogram.py failed.
    echo Check PostgreSQL configuration, table availability,
    echo and Python dependencies.
    pause
    exit /b 1
)

echo.
echo [2/4] Completed successfully.
echo.

REM ------------------------------------------------------------
REM Step 3: Regenerate vertical histogram visualizations
REM ------------------------------------------------------------
echo [3/4] Generating vertical histogram visualizations...
python code\plot_histogram.py

if errorlevel 1 (
    echo.
    echo ERROR: plot_histogram.py failed.
    pause
    exit /b 1
)

echo.
echo [3/4] Completed successfully.
echo.

REM ------------------------------------------------------------
REM Step 4: Generate exchanged-axes/horizontal-bar plots
REM ------------------------------------------------------------
echo [4/4] Generating exchanged-axes histogram visualizations...
python code\plot.py

if errorlevel 1 (
    echo.
    echo ERROR: plot.py failed.
    pause
    exit /b 1
)

echo.
echo [4/4] Completed successfully.
echo.

echo ============================================================
echo SUCCESS
echo ============================================================
echo.
echo The complete experiment has finished successfully.
echo.
echo Generated results are available in:
echo %cd%\results
echo.
echo Important files:
echo   experiment_results.csv
echo   full_table_extrapolation.csv
echo   *_trials_*.csv
echo   *_boundaries_*.csv
echo   *_errors_*.csv
echo   *_metadata_*.csv
echo   q1_*_histogram.png
echo   *_histogram_*.png
echo   sample_size_vs_error.png
echo   sample_size_vs_time.png
echo   vertical_histograms\
echo.
pause

endlocal
```
