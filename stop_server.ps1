# Windows Desktop Agent Server Stopper
[CmdletBinding()]
param(
    [int]$Port = 8765
)

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "          Stopping Desktop Agent Server (Port $Port)            " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

$Connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($Connections) {
    $Pids = $Connections.OwningProcess | Select-Object -Unique
    foreach ($p in $Pids) {
        Write-Host "[INFO] Stopping server process (PID: $p)..." -ForegroundColor Yellow
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        Write-Host "[OK] Process $p stopped." -ForegroundColor Green
    }
} else {
    Write-Host "[INFO] No server found listening on port $Port." -ForegroundColor Gray
}

Write-Host "[DONE] Cleanup completed." -ForegroundColor Cyan

