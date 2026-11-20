[CmdletBinding()]
param([switch]$SkipStart)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path $PSScriptRoot).Path
$backendDir = Join-Path $projectRoot 'backend'
$frontendDir = Join-Path $projectRoot 'frontend'
$agentDir = Join-Path $projectRoot 'agent'
$venvDir = Join-Path $backendDir '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$agentVenvDir = Join-Path $agentDir '.venv'
$agentVenvPython = Join-Path $agentVenvDir 'Scripts\python.exe'

if (-not (Test-Path (Join-Path $backendDir 'pyproject.toml')) -or -not (Test-Path (Join-Path $frontendDir 'package.json'))) {
    throw 'Run this installer from the extracted SentinelWatch project folder.'
}

$pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
$pythonCommand = $null
$pythonPrefix = @()
if ($pyLauncher) {
    & $pyLauncher.Source -3.12 -c 'import sys; assert sys.version_info >= (3, 12)'
    if ($LASTEXITCODE -eq 0) {
        $pythonCommand = $pyLauncher.Source
        $pythonPrefix = @('-3.12')
    }
}
if (-not $pythonCommand) {
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $python) { throw 'Python 3.12 or newer is required. Install Python, then run this installer again.' }
    & $python.Source -c 'import sys; assert sys.version_info >= (3, 12), "Python 3.12 or later is required"'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 or later is required.' }
    $pythonCommand = $python.Source
}
$node = Get-Command node.exe -ErrorAction SilentlyContinue
$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $node -or -not $npm) { throw 'Node.js 20 or later (with npm) is required. Install it, then run this installer again.' }
$nodeVersion = (& $node.Source --version).Trim(); $nodeMajor = [int]($nodeVersion.Substring(1).Split('.')[0])
if ($nodeMajor -lt 20) { throw "Node.js 20 or later is required. Found $(& $node.Source --version)." }

# Keep generated machine-specific settings out of Git and never replace a user's values.
$envPath = Join-Path $projectRoot '.env'
if (-not (Test-Path $envPath)) { Copy-Item (Join-Path $projectRoot '.env.example') $envPath }
$envLines = @(Get-Content -LiteralPath $envPath)
$secretLineIndex = -1
for ($i = 0; $i -lt $envLines.Count; $i++) {
    if ($envLines[$i] -match '^\s*SW_BACKEND_AUTH__JWT_SECRET=') { $secretLineIndex = $i; break }
}
$jwtSecret = if ($secretLineIndex -ge 0) { ($envLines[$secretLineIndex] -split '=', 2)[1].Trim() } else { '' }
if (-not $jwtSecret -or $jwtSecret -eq 'CHANGE_ME_IN_PRODUCTION_USE_STRONG_RANDOM_KEY') {
    $jwtSecret = (& $pythonCommand @pythonPrefix -c 'import secrets; print(secrets.token_hex(32))').Trim()
    if ($LASTEXITCODE -ne 0 -or $jwtSecret.Length -lt 64) { throw 'Could not generate the local JWT signing key.' }
    if ($secretLineIndex -ge 0) {
        $envLines[$secretLineIndex] = "SW_BACKEND_AUTH__JWT_SECRET=$jwtSecret"
    } else {
        $envLines += "SW_BACKEND_AUTH__JWT_SECRET=$jwtSecret"
    }
    Set-Content -LiteralPath $envPath -Value $envLines -Encoding UTF8
}

foreach ($line in Get-Content -LiteralPath $envPath) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim(), 'Process')
    }
}

$backendConfig = Join-Path $backendDir 'config\backend.yaml'
if (-not (Test-Path $backendConfig)) {
    Copy-Item (Join-Path $backendDir 'config\backend.yaml.example') $backendConfig
}
New-Item -ItemType Directory -Force -Path (Join-Path $backendDir 'data'), (Join-Path $backendDir 'logs'), (Join-Path $projectRoot 'logs') | Out-Null

if (-not (Test-Path $venvPython)) {
    Write-Host 'Creating the backend Python environment...' -ForegroundColor Cyan
    & $pythonCommand @pythonPrefix -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
Write-Host 'Installing backend dependencies...' -ForegroundColor Cyan
Push-Location $backendDir
try {
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'Could not update pip.' }
    & $venvPython -m pip install -e '.[sqlite]'
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
} finally { Pop-Location }

if (-not (Test-Path $agentVenvPython)) {
    Write-Host 'Creating the Windows agent Python environment...' -ForegroundColor Cyan
    & $pythonCommand @pythonPrefix -m venv $agentVenvDir
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the agent Python environment.' }
}
Write-Host 'Installing Windows agent dependencies...' -ForegroundColor Cyan
Push-Location $agentDir
try {
    & $agentVenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'Could not update pip for the endpoint agent.' }
    & $agentVenvPython -m pip install -e '.[compression]'
    if ($LASTEXITCODE -ne 0) { throw 'Windows agent dependency installation failed.' }
} finally { Pop-Location }

Write-Host 'Installing dashboard dependencies...' -ForegroundColor Cyan
Push-Location $frontendDir
try {
    & npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Dashboard dependency installation failed.' }
} finally { Pop-Location }

Write-Host 'SentinelWatch backend, Windows agent and dashboard are installed. Local JWT key is stored in the ignored .env file.' -ForegroundColor Green
if (-not $SkipStart) {
    & (Join-Path $projectRoot 'scripts\start.ps1')
}
