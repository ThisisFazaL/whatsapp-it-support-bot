@echo off
title Tagoneswa Favlogix Bridge Worker (Port 8000)
cd /d "%~dp0\.."
echo ========================================================
echo   Tagoneswa Favlogix Bridge Worker Service
echo ========================================================

if exist ".\venv\Scripts\activate.bat" (
    call ".\venv\Scripts\activate.bat"
) else (
    echo Virtual environment not found. Using system Python...
)

echo Testing Chrome port 9222 connectivity...
curl -s http://127.0.0.1:9222/json/version >nul
if %errorlevel% neq 0 (
    echo [WARNING] Chrome port 9222 is not open! Launching Chrome first...
    call worker\start_chrome_worker.bat
)

echo Starting FastAPI Bridge on port 8000...
:LOOP
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
echo Server stopped. Restarting in 5 seconds...
timeout /t 5 >nul
goto LOOP
