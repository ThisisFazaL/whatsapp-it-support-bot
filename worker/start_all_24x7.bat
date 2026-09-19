@echo off
title Tagoneswa 24x7 Worker Launcher
cd /d "%~dp0"
echo ========================================================
echo   Launching All 24x7 Favlogix Automation Services
echo ========================================================

REM 1. Start Chrome
call start_chrome_worker.bat

REM 2. Start Ngrok Tunnel in background window
start "Ngrok Tunnel (Port 8000)" cmd /k "ngrok http 8000 --url=uninjured-seducing-cycle.ngrok-free.dev"

REM 3. Start Python Bridge Service
start "Favlogix Bridge (Port 8000)" call start_bridge_service.bat

echo ========================================================
echo   ALL SERVICES LAUNCHED!
echo ========================================================
echo 1. Chrome is running on Port 9222 with dedicated profile
echo 2. Ngrok is forwarding traffic to port 8000
echo 3. FastAPI Bridge is listening for Render requests
echo.
echo Please log into your real ERP in the Chrome window once.
echo The session will remain permanently active in C:\FavlogixWorkerProfile.
echo ========================================================
pause
