[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$workspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$backendDirectory = Join-Path $workspace "backend"
$frontendDirectory = Join-Path $workspace "frontend"
$python = Join-Path $workspace ".venv\Scripts\python.exe"
$backendEnv = Join-Path $backendDirectory ".env"
$frontendEnv = Join-Path $frontendDirectory ".env.local"
$runtimeDirectory = Join-Path $backendDirectory ".runtime"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Missing .venv Python at $python. Create or restore the workspace virtual environment."
}
if (-not (Test-Path -LiteralPath $backendEnv -PathType Leaf)) {
    throw "Missing backend/.env. Copy backend/.env.example to backend/.env."
}
if (-not (Test-Path -LiteralPath $frontendEnv -PathType Leaf)) {
    throw "Missing frontend/.env.local. Copy frontend/.env.example to frontend/.env.local."
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendDirectory "node_modules") -PathType Container)) {
    throw "Missing frontend dependencies. Run npm ci in frontend/."
}

New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
$stdoutLog = Join-Path $runtimeDirectory "uvicorn.stdout.log"
$stderrLog = Join-Path $runtimeDirectory "uvicorn.stderr.log"

$backend = Start-Process `
    -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $backendDirectory `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -WindowStyle Hidden `
    -PassThru

try {
    $healthy = $false
    foreach ($attempt in 1..30) {
        if ($backend.HasExited) {
            $details = if (Test-Path -LiteralPath $stderrLog) {
                Get-Content -LiteralPath $stderrLog -Raw
            } else {
                "No backend error log was produced."
            }
            throw "Backend exited during startup. $details"
        }
        try {
            $response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 1
            if ($response.status -eq "ok") {
                $healthy = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $healthy) {
        throw "Backend did not become healthy within 15 seconds. See $stderrLog"
    }

    Write-Host "Backend healthy at http://127.0.0.1:8000/api/health"
    Write-Host "Starting frontend at http://localhost:3000"
    Push-Location $frontendDirectory
    try {
        & npm run dev
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend exited with code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
} finally {
    if (-not $backend.HasExited) {
        Stop-Process -Id $backend.Id
        $backend.WaitForExit()
    }
}
