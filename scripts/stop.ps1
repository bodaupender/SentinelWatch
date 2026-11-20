$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runDir = Join-Path $projectRoot '.run'
$expected = @{
    agent = 'sentinelwatch_agent.main'
    backend = Join-Path $projectRoot 'backend\src'
    frontend = Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js'
}
foreach ($name in @('agent', 'backend', 'frontend')) {
    $pidPath = Join-Path $runDir "$name.pid"
    if (-not (Test-Path $pidPath)) { continue }
    $processId = 0
    [void][int]::TryParse((Get-Content -LiteralPath $pidPath -Raw).Trim(), [ref]$processId)
    $proc = if ($processId -gt 0) { Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue }
    if ($proc -and ($proc.CommandLine.IndexOf($expected[$name], [StringComparison]::OrdinalIgnoreCase) -ge 0 -or ($name -eq 'agent' -and $proc.ExecutablePath.IndexOf((Join-Path $projectRoot 'agent'), [StringComparison]::OrdinalIgnoreCase) -ge 0))) {
        & taskkill.exe /T /F /PID $processId | Out-Null
        Write-Host "Stopped $name (PID $processId)." -ForegroundColor Green
    } elseif ($proc) {
        Write-Warning "PID $processId no longer identifies this SentinelWatch service; leaving it running."
    } else {
        Write-Host "$name is already stopped." -ForegroundColor DarkGray
    }
    Remove-Item -LiteralPath $pidPath -Force
}
