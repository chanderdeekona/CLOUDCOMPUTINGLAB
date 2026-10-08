@echo off
TITLE Cloud Security Alert Lamp - Demo Launcher
echo ===================================================================
echo     CLOUD SECURITY ALERT LAMP - FULL-STACK SYSTEM LAUNCHER
echo     AWS S3 Public Bucket Detection & Real-Time IoT Monitoring
echo ===================================================================
echo.

set "NODE_PATH=%USERPROFILE%\bin\node-v20.18.0-win-x64"
if exist "%NODE_PATH%\node.exe" (
    set "PATH=%NODE_PATH%;%PATH%"
)

echo [1/3] Starting FastAPI Backend on http://localhost:8000 ...
start "Cloud Security Alert Lamp - Backend" cmd /k "..\venv\Scripts\python.exe main.py" /d "%~dp0backend"

timeout /t 3 /nobreak >nul

echo [2/3] Starting React Frontend on http://localhost:5173 ...
start "Cloud Security Alert Lamp - Frontend" cmd /k "npm run dev" /d "%~dp0frontend"

timeout /t 3 /nobreak >nul

echo [3/3] Opening Dashboard in default web browser...
start http://localhost:5173

echo.
echo ===================================================================
echo System started successfully!
echo - Web Dashboard : http://localhost:5173
echo - API & Swagger : http://localhost:8000/docs
echo - WebSocket     : ws://localhost:8000/ws
echo.
echo To run the Physical IoT LED Controller (or Desktop Terminal Simulator):
echo Run: venv\Scripts\python.exe iot\led_controller.py
echo ===================================================================
pause
