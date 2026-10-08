# Cloud Security Alert Lamp - PowerShell Launcher

$nodePath = "$env:USERPROFILE\bin\node-v20.18.0-win-x64"
if (Test-Path "$nodePath\node.exe") {
    $env:Path = "$nodePath;$env:Path"
}

Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "    CLOUD SECURITY ALERT LAMP - FULL-STACK SYSTEM LAUNCHER         " -ForegroundColor Yellow
Write-Host "    AWS S3 Public Bucket Detection & Real-Time IoT Monitoring      " -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Cyan

# 1. Start Backend in separate process
Write-Host "[1/3] Starting FastAPI Backend on http://localhost:8000 ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd backend; ..\venv\Scripts\python.exe main.py"

Start-Sleep -Seconds 3

# 2. Start Frontend in separate process
Write-Host "[2/3] Starting React Frontend on http://localhost:5173 ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:Path = '$nodePath;' + `$env:Path; cd frontend; npm run dev"

Start-Sleep -Seconds 3

# 3. Open Browser
Write-Host "[3/3] Opening Dashboard in browser..." -ForegroundColor Green
Start-Process "http://localhost:5173"

Write-Host "`nAll services running!" -ForegroundColor Green
Write-Host "- Dashboard: http://localhost:5173" -ForegroundColor White
Write-Host "- API Docs : http://localhost:8000/docs" -ForegroundColor White
Write-Host "`nTo start the Physical LED / Simulator, run in another terminal:" -ForegroundColor Yellow
Write-Host ".\venv\Scripts\python.exe iot\led_controller.py" -ForegroundColor Yellow
