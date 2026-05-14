$root   = Split-Path $PSScriptRoot -Parent
$apiDir = "$root\apps\api"
$venv   = "$apiDir\.venv"
$python = "$venv\Scripts\python.exe"
$pip    = "$venv\Scripts\pip.exe"
$main   = "$root\apps\desktop\main.py"

Write-Host ""
Write-Host "  App Prospection" -ForegroundColor Cyan
Write-Host ""

# ── 1. Vérifier que Python est disponible ────────────────────────────────────
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "  ERREUR : Python introuvable." -ForegroundColor Red
    Write-Host "  Installe Python 3.11+ depuis https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  Coche bien 'Add Python to PATH' lors de l'installation." -ForegroundColor Yellow
    Read-Host "`n  Appuie sur Entrée pour fermer"
    exit 1
}

# ── 2. Créer le venv si absent ───────────────────────────────────────────────
if (-not (Test-Path $python)) {
    Write-Host "  Premier lancement : création de l'environnement virtuel..." -ForegroundColor Yellow
    Push-Location $apiDir
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERREUR : impossible de créer le venv." -ForegroundColor Red
        Pop-Location
        Read-Host "`n  Appuie sur Entrée pour fermer"
        exit 1
    }
    Pop-Location
    Write-Host "  Environnement virtuel créé." -ForegroundColor Green
}

# ── 3. Installer / mettre à jour les dépendances ─────────────────────────────
Write-Host "  Vérification des dépendances..." -ForegroundColor Gray
& $pip install -r "$apiDir\requirements.txt" --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERREUR : échec de l'installation des dépendances." -ForegroundColor Red
    Read-Host "`n  Appuie sur Entrée pour fermer"
    exit 1
}

# ── 4. Vérifier que .env existe ──────────────────────────────────────────────
$envFile     = "$root\.env"
$envExample  = "$root\.env.example"
if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-Host ""
        Write-Host "  ATTENTION : le fichier .env a été créé depuis .env.example." -ForegroundColor Yellow
        Write-Host "  Ouvre-le et renseigne tes identifiants Gmail avant d'utiliser l'app :" -ForegroundColor Yellow
        Write-Host "  $envFile" -ForegroundColor Cyan
        Write-Host ""
        Read-Host "  Appuie sur Entrée pour lancer l'app quand même (certaines fonctions seront indisponibles)"
    } else {
        Write-Host "  ERREUR : fichier .env introuvable et .env.example absent." -ForegroundColor Red
        Read-Host "`n  Appuie sur Entrée pour fermer"
        exit 1
    }
}

# ── 5. Créer les dossiers de données si absents ──────────────────────────────
@("$root\data\imports", "$root\data\exports") | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ | Out-Null }
}

# ── 6. Lancer l'application ──────────────────────────────────────────────────
Write-Host "  Lancement..." -ForegroundColor Green
Write-Host ""
& $python $main
