@echo off
title Favlogix Chrome 24x7 Worker
echo ========================================================
echo   Starting Google Chrome for 24x7 Favlogix Automation
echo ========================================================
echo Remote Debugging Port: 9222
echo Profile Directory:     C:\FavlogixWorkerProfile
echo Anti-throttling flags: Active (Prevents background sleep)
echo ========================================================

REM Find Chrome installation path
set CHROME_EXE=
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" set CHROME_EXE="C:\Program Files\Google\Chrome\Application\chrome.exe"
if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" set CHROME_EXE="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set CHROME_EXE="%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"

if "%CHROME_EXE%"=="" (
    echo [ERROR] Google Chrome was not found in standard directories.
    echo Please install Google Chrome from https://www.google.com/chrome/
    pause
    exit /b 1
)

REM Check if port 9222 is already open
netstat -ano | findstr :9222 >nul
if %errorlevel% equ 0 (
    echo [OK] Chrome is already running and listening on port 9222.
    exit /b 0
)

echo Launching Chrome...
start "" %CHROME_EXE% ^
  --remote-debugging-port=9222 ^
  --user-data-dir="C:\FavlogixWorkerProfile" ^
  --no-first-run ^
  --no-default-browser-check ^
  --disable-features=Translate ^
  --disable-background-timer-throttling ^
  --disable-backgrounding-occluded-windows ^
  --disable-renderer-backgrounding

timeout /t 3 /nobreak >nul
echo [SUCCESS] Chrome launched successfully on port 9222!
