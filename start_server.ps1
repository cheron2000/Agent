# Windows Desktop Agent Server Launcher (Hands & Eyes Engine)
[CmdletBinding()]
param(
    [switch]$Background,
    [switch]$Restart,
    [int]$Port = 8765
)

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "      Desktop Agent Server Launcher (Hands & Eyes Engine)       " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# 1. Resolve Python binary (prefer venv)
$VenvPython = Join-Path $RootDir "venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonBin = $VenvPython
    Write-Host "[OK] Using virtualenv Python: $PythonBin" -ForegroundColor Green
} else {
    $PythonBin = "python"
    Write-Host "[OK] Using system Python: $PythonBin" -ForegroundColor Green
}

# 2. Check if server port is already listening
$ExistingConn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($ExistingConn) {
    $ExistingPid = $ExistingConn.OwningProcess | Select-Object -First 1
    Write-Host ""
    Write-Host "[INFO] Server is ALREADY running on port $Port (PID: $ExistingPid)" -ForegroundColor Yellow
    Write-Host "[INFO] Endpoint: http://127.0.0.1:$Port" -ForegroundColor Yellow
    
    $shouldRestart = $Restart
    if (-not $shouldRestart -and [Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
        $ans = Read-Host "Server is already running. Restart it now? (y/N, default=N)"
        if ($ans -match '^[yY]') {
            $shouldRestart = $true
        }
    }

    if ($shouldRestart) {
        Write-Host "[INFO] Stopping existing server process (PID: $ExistingPid)..." -ForegroundColor Yellow
        Stop-Process -Id $ExistingPid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    } else {
        Write-Host "[INFO] Keeping existing server running." -ForegroundColor Gray
        Write-Host "[INFO] Run 'stop_server.bat' to terminate the existing server if needed." -ForegroundColor Yellow
        Write-Host ""
        if ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
            Start-Sleep -Seconds 2
        }
        exit 0
    }
}

# 3. Launch server
$ServerScript = Join-Path $RootDir "agent_server.py"

if ($Background) {
    Write-Host "[INFO] Launching Desktop Agent Server in the background..." -ForegroundColor Cyan
    $proc = Start-Process -FilePath $PythonBin -ArgumentList "`"$ServerScript`"" -WorkingDirectory $RootDir -PassThru
    Start-Sleep -Seconds 3
    Write-Host "[OK] Server started in background (PID: $($proc.Id)) on http://127.0.0.1:$Port" -ForegroundColor Green
    Write-Host "[INFO] To stop the server at any time, run 'stop_server.bat'." -ForegroundColor Gray
} else {
    Write-Host "[INFO] Starting Desktop Agent Server on http://127.0.0.1:$Port..." -ForegroundColor Cyan
    Write-Host "[INFO] Auth Token is saved in: $(Join-Path $RootDir '.agent_token')" -ForegroundColor Gray
    Write-Host "[INFO] Press Ctrl+C anytime to stop." -ForegroundColor Gray
    Write-Host ""
    & $PythonBin $ServerScript
    if ($LASTEXITCODE -ne 0 -and [Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
        Write-Host "[ERROR] Server exited with code $LASTEXITCODE." -ForegroundColor Red
        Read-Host "Press Enter to exit..."
    }
}
