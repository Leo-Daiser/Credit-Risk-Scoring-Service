[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}

Write-Host "Preparing trusted local ML artifacts..."
& $python -m src.cli prepare-local-ml
if ($LASTEXITCODE -ne 0) {
    throw "Public Profile ML preparation failed. The demo was not started."
}

Write-Host "Starting Riskline demo stack..."
& docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose failed to start the demo stack."
}

$ready = $null
for ($attempt = 1; $attempt -le 60; $attempt++) {
    try {
        $ready = Invoke-RestMethod -Uri "http://localhost:8000/ready" -TimeoutSec 3
        break
    }
    catch {
        Start-Sleep -Seconds 2
    }
}
if ($null -eq $ready) {
    & docker compose -f docker-compose.yml -f docker-compose.demo.yml ps
    throw "Riskline API did not become ready within 120 seconds."
}

& docker compose -f docker-compose.yml -f docker-compose.demo.yml exec -T api python -m src.cli verify-demo
if ($LASTEXITCODE -ne 0) {
    throw "Demo verification failed."
}

Write-Host ""
Write-Host "Riskline demo ready"
Write-Host "Frontend: http://localhost:3000"
Write-Host "API:      http://localhost:8000"
Write-Host "Full model:       $($ready.full_model_available)"
Write-Host "Public Profile ML: $(if ($ready.public_model_available) { 'ACTIVE' } else { 'INACTIVE' })"
Write-Host "Offer ranker:      $(if ($ready.offer_ranker_available) { 'ML artifact available' } else { 'rules mode' })"
Write-Host "Synthetic offers:  verified by verify-demo"
