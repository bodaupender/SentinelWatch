[CmdletBinding()]
param(
    [string]$BackendHost = '127.0.0.1',
    [int]$BackendPort = 8001,
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendDir = Join-Path $projectRoot 'backend'
$backendPython = Join-Path $backendDir '.venv\Scripts\python.exe'
$frontendDir = Join-Path $projectRoot 'frontend'
$agentDir = Join-Path $projectRoot 'agent'
$viteCli = Join-Path $frontendDir 'node_modules\vite\bin\vite.js'
$node = (Get-Command node.exe -ErrorAction SilentlyContinue).Source
$runDir = Join-Path $projectRoot '.run'

if (-not (Test-Path $backendPython)) {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw 'Python 3.12 or newer is required. Run .\install.ps1 or install Python first.' }
    $backendPython = $pythonCommand.Source
    & $backendPython -c 'import fastapi, uvicorn, sqlalchemy, aiosqlite, jose, passlib, ruamel.yaml'
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependencies are missing. Run .\install.ps1 first.' }
}
if (-not $node -or -not (Test-Path $viteCli)) { throw 'Dashboard is not installed. Run .\install.ps1 first.' }

$envPath = Join-Path $projectRoot '.env'
if (-not (Test-Path $envPath)) {
    Copy-Item -LiteralPath (Join-Path $projectRoot '.env.example') -Destination $envPath
}
$envLines = @(Get-Content -LiteralPath $envPath)
$secretIndex = -1
for ($i = 0; $i -lt $envLines.Count; $i++) {
    if ($envLines[$i] -match '^\s*SW_BACKEND_AUTH__JWT_SECRET=(.*)$') { $secretIndex = $i; break }
}
$localSecret = if ($secretIndex -ge 0) { ($envLines[$secretIndex] -split '=', 2)[1].Trim() } else { '' }
if (-not $localSecret -or $localSecret -eq 'CHANGE_ME_IN_PRODUCTION_USE_STRONG_RANDOM_KEY') {
    $localSecret = (& $backendPython -c 'import secrets; print(secrets.token_hex(32))').Trim()
    if ($LASTEXITCODE -ne 0 -or $localSecret.Length -lt 64) { throw 'Could not create the local JWT signing key.' }
    if ($secretIndex -ge 0) { $envLines[$secretIndex] = "SW_BACKEND_AUTH__JWT_SECRET=$localSecret" }
    else { $envLines += "SW_BACKEND_AUTH__JWT_SECRET=$localSecret" }
    Set-Content -LiteralPath $envPath -Value $envLines -Encoding UTF8
}
if (Test-Path $envPath) {
    foreach ($line in Get-Content -LiteralPath $envPath) {
        if ($line -match '^\s*(SW_BACKEND_[A-Z0-9_]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim(), 'Process')
        }
    }
}
$enrollmentIndex = -1
for ($i = 0; $i -lt $envLines.Count; $i++) {
    if ($envLines[$i] -match '^\s*SW_BACKEND_AGENT_ENROLLMENT_TOKEN=(.*)$') { $enrollmentIndex = $i; break }
}
$enrollmentToken = if ($enrollmentIndex -ge 0) { ($envLines[$enrollmentIndex] -split '=', 2)[1].Trim() } else { '' }
if (-not $enrollmentToken -or $enrollmentToken.Length -lt 32) {
    $enrollmentToken = (& $backendPython -c 'import secrets; print(secrets.token_urlsafe(48))').Trim()
    if ($LASTEXITCODE -ne 0 -or $enrollmentToken.Length -lt 48) { throw 'Could not create the local agent enrollment token.' }
    if ($enrollmentIndex -ge 0) { $envLines[$enrollmentIndex] = "SW_BACKEND_AGENT_ENROLLMENT_TOKEN=$enrollmentToken" }
    else { $envLines += "SW_BACKEND_AGENT_ENROLLMENT_TOKEN=$enrollmentToken" }
    Set-Content -LiteralPath $envPath -Value $envLines -Encoding UTF8
    Write-Host 'Created a secure local agent enrollment token in .env.' -ForegroundColor DarkGray
}
foreach ($line in Get-Content -LiteralPath $envPath) {
    if ($line -match '^\s*SW_BACKEND_AGENT_ENROLLMENT_TOKEN=(.*)$') {
        [Environment]::SetEnvironmentVariable('SW_BACKEND_AGENT_ENROLLMENT_TOKEN', $Matches[1].Trim(), 'Process')
    }
}
$agentPython = Join-Path $agentDir 'venv\Scripts\python.exe'
if (-not (Test-Path $agentPython)) { $agentPython = (Get-Command python.exe -ErrorAction Stop).Source }
& $agentPython -c 'import psutil, win32evtlog, pydantic_settings, cryptography, structlog, tenacity' 2>$null
if ($LASTEXITCODE -ne 0) {
    $agentPython = (Get-Command python.exe -ErrorAction Stop).Source
    & $agentPython -c 'import psutil, win32evtlog, pydantic_settings, cryptography, structlog, tenacity' 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Endpoint agent dependencies are missing. Install the agent requirements first.' }
}
$env:PYTHONPATH = Join-Path $backendDir 'src'
New-Item -ItemType Directory -Force -Path $runDir, (Join-Path $backendDir 'logs'), (Join-Path $frontendDir 'logs'), (Join-Path $agentDir 'logs') | Out-Null

function Test-HttpEndpoint([string]$Url) {
    try { $null = Invoke-RestMethod -Uri $Url -TimeoutSec 2; return $true }
    catch { return $false }
}

function Start-LoggedProcess([string]$Name, [string]$FilePath, [string]$Arguments, [string]$WorkingDirectory) {
    $pidPath = Join-Path $runDir "$Name.pid"
    if (Test-Path $pidPath) {
        $oldPid = 0
        [void][int]::TryParse((Get-Content -LiteralPath $pidPath -Raw).Trim(), [ref]$oldPid)
        $oldProcess = if ($oldPid -gt 0) { Get-CimInstance Win32_Process -Filter "ProcessId = $oldPid" -ErrorAction SilentlyContinue }
        if ($oldProcess -and $oldProcess.CommandLine.IndexOf($projectRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            throw "$Name is already running (PID $oldPid). Use .\scripts\stop.ps1 to stop it first."
        }
        Remove-Item -LiteralPath $pidPath -Force
    }
    $outLog = Join-Path $WorkingDirectory 'logs\launcher.stdout.log'
    $errLog = Join-Path $WorkingDirectory 'logs\launcher.stderr.log'
    $proc = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
    Set-Content -LiteralPath $pidPath -Value $proc.Id -NoNewline
    return $proc
}

$backend = $null
$frontend = $null
$agent = $null
$startedProcesses = @()
try {
    $backendReady = Test-HttpEndpoint "http://127.0.0.1:$BackendPort/health"
    if ($backendReady) {
        Write-Host "Backend is already healthy on port $BackendPort; reusing it." -ForegroundColor DarkGray
    } else {
        $backendArgs = "-m uvicorn --factory --app-dir `"$(Join-Path $backendDir 'src')`" sentinelwatch_backend.main:create_app --host $BackendHost --port $BackendPort"
        $backend = Start-LoggedProcess 'backend' $backendPython $backendArgs $backendDir
        $startedProcesses += [PSCustomObject]@{ Name = 'backend'; Process = $backend }
        for ($i = 0; $i -lt 45; $i++) {
            if (Test-HttpEndpoint "http://127.0.0.1:$BackendPort/health") { $backendReady = $true; break }
            if ($backend.HasExited) { break }
            Start-Sleep -Seconds 1
        }
        if (-not $backendReady) { throw "Backend failed its health check. Read $backendDir\logs\launcher.stderr.log." }
    }

    $frontendReady = Test-HttpEndpoint "http://127.0.0.1:$FrontendPort/"
    if ($frontendReady) {
        Write-Host "Dashboard is already responding on port $FrontendPort; reusing it." -ForegroundColor DarkGray
    } else {
        $frontendArgs = "`"$viteCli`" --host 127.0.0.1 --port $FrontendPort --strictPort"
        $frontend = Start-LoggedProcess 'frontend' $node $frontendArgs $frontendDir
        $startedProcesses += [PSCustomObject]@{ Name = 'frontend'; Process = $frontend }
        for ($i = 0; $i -lt 30; $i++) {
            if (Test-HttpEndpoint "http://127.0.0.1:$FrontendPort/") { $frontendReady = $true; break }
            if ($frontend.HasExited) { break }
            Start-Sleep -Seconds 1
        }
        if (-not $frontendReady) { throw "Dashboard failed its health check. Read $frontendDir\logs\launcher.stderr.log." }
    }

    $agentPidPath = Join-Path $runDir 'agent.pid'
    $agentReady = $false
    if (Test-Path $agentPidPath) {
        $oldAgentPid = 0
        [void][int]::TryParse((Get-Content -LiteralPath $agentPidPath -Raw).Trim(), [ref]$oldAgentPid)
        $oldAgent = if ($oldAgentPid -gt 0) { Get-CimInstance Win32_Process -Filter "ProcessId = $oldAgentPid" -ErrorAction SilentlyContinue }
        if ($oldAgent -and $oldAgent.CommandLine.IndexOf('sentinelwatch_agent.main', [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $agentReady = $true
            Write-Host "Endpoint agent is already running (PID $oldAgentPid); reusing it." -ForegroundColor DarkGray
        } else { Remove-Item -LiteralPath $agentPidPath -Force }
    }
    if (-not $agentReady) {
        $env:SW_AGENT_BACKEND__URL = "http://127.0.0.1:$BackendPort"
        $env:SW_AGENT_AGENT__ENROLLMENT_TOKEN = $enrollmentToken
        $previousPythonPath = $env:PYTHONPATH
        $env:PYTHONPATH = Join-Path $agentDir 'src'
        try {
            $agent = Start-LoggedProcess 'agent' $agentPython '-m sentinelwatch_agent.main' $agentDir
            $startedProcesses += [PSCustomObject]@{ Name = 'agent'; Process = $agent }
        } finally { $env:PYTHONPATH = $previousPythonPath }
        Start-Sleep -Seconds 3
        if ($agent.HasExited) { throw "Endpoint agent failed to start. Read $agentDir\logs\launcher.stderr.log." }
        Write-Host "Endpoint agent started (PID $($agent.Id))." -ForegroundColor Green
    }

    Write-Host "Backend is healthy: http://127.0.0.1:$BackendPort/health" -ForegroundColor Green
    Write-Host "Dashboard: http://127.0.0.1:$FrontendPort" -ForegroundColor Green
    Write-Host 'Endpoint collection: enabled locally; telemetry is sent to this PC SentinelWatch backend.' -ForegroundColor DarkGray
    Write-Host 'Create your first analyst account from the dashboard registration page.' -ForegroundColor Cyan
    Write-Host 'Stop the local agent, backend, and dashboard with .\scripts\stop.ps1.' -ForegroundColor Cyan
    Start-Process "http://127.0.0.1:$FrontendPort"
} catch {
    foreach ($entry in $startedProcesses) {
        $processId = $entry.Process.Id
        $current = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        if ($current -and ($current.CommandLine.IndexOf($projectRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or ($entry.Name -eq 'agent' -and $current.CommandLine.IndexOf('sentinelwatch_agent.main', [StringComparison]::OrdinalIgnoreCase) -ge 0))) {
            & taskkill.exe /T /F /PID $processId | Out-Null
        }
        $pidPath = Join-Path $runDir "$($entry.Name).pid"
        if (Test-Path $pidPath) {
            $savedPid = 0
            [void][int]::TryParse((Get-Content -LiteralPath $pidPath -Raw).Trim(), [ref]$savedPid)
            if ($savedPid -eq $processId) { Remove-Item -LiteralPath $pidPath -Force }
        }
    }
    throw
}
