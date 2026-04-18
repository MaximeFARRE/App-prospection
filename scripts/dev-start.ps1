$root = Split-Path $PSScriptRoot -Parent
$python = "$root\apps\api\.venv\Scripts\python.exe"
$main   = "$root\apps\desktop\main.py"

Write-Host ""
Write-Host "  App Prospection" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $python)) {
    Write-Host "  ERREUR : environnement virtuel introuvable." -ForegroundColor Red
    Write-Host "  Lance d'abord :" -ForegroundColor Yellow
    Write-Host "    cd apps\api" -ForegroundColor Yellow
    Write-Host "    python -m venv .venv" -ForegroundColor Yellow
    Write-Host "    .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

& $python $main
