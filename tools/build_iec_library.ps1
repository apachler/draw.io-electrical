# build_iec_library.ps1
# Konvertierungspipeline: qelectrotech-elements -> draw.io Bibliothek
#
# Aufruf mit Parameter:
#   powershell -ExecutionPolicy Bypass -File tools\build_iec_library.ps1 -ForkDir C:\...\draw.io-electrical
#
# Aufruf interaktiv (ohne Parameter):
#   powershell -ExecutionPolicy Bypass -File tools\build_iec_library.ps1

param(
    [string]$ForkDir = ""
)

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

function Write-Ok   { param($msg) Write-Host "  [OK]  $msg" -ForegroundColor Green }
function Write-Info { param($msg) Write-Host "  [..] $msg"  -ForegroundColor Cyan  }
function Write-Warn { param($msg) Write-Host "  [!!] $msg"  -ForegroundColor Yellow }
function Write-Err  { param($msg) Write-Host "  [ERR] $msg" -ForegroundColor Red   }

# ---------------------------------------------------------------------------
# Schritt 1 — ForkDir ermitteln
# ---------------------------------------------------------------------------

if (-not $ForkDir) {
    $ForkDir = Read-Host "Pfad zum Fork-Verzeichnis (draw.io-electrical)"
}

$ForkDir = $ForkDir.Trim('"').Trim("'")

if (-not (Test-Path $ForkDir)) {
    Write-Err "Verzeichnis nicht gefunden: $ForkDir"
    exit 1
}

Write-Info "ForkDir: $ForkDir"

# ---------------------------------------------------------------------------
# Schritt 2 — qelectrotech-elements Submodul pruefen
# ---------------------------------------------------------------------------

$qetElementsDir = Join-Path $ForkDir "qelectrotech-elements\elements"

if (-not (Test-Path $qetElementsDir)) {
    Write-Warn "qelectrotech-elements/elements/ nicht gefunden. Initialisiere Submodul..."
    & git -C $ForkDir submodule update --init --recursive
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Submodul-Initialisierung fehlgeschlagen."
        exit 1
    }
}

$hasElmt = (Get-ChildItem $qetElementsDir -Filter "*.elmt" -Recurse -ErrorAction SilentlyContinue |
                Select-Object -First 1) -ne $null

if (-not $hasElmt) {
    Write-Err "Keine .elmt-Dateien in $qetElementsDir gefunden."
    Write-Info "Manuell: git -C '$ForkDir' submodule update --init --recursive"
    exit 1
}

Write-Ok ".elmt-Dateien gefunden in $qetElementsDir"

# ---------------------------------------------------------------------------
# Schritt 3 — Verzeichnisse anlegen
# ---------------------------------------------------------------------------

$sourceDir = Join-Path $ForkDir "source"
$outputDir = Join-Path $ForkDir "output"

foreach ($dir in @($sourceDir, $outputDir)) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
        Write-Ok "Verzeichnis angelegt: $dir"
    }
}

# ---------------------------------------------------------------------------
# Schritt 4 — Python finden
# ---------------------------------------------------------------------------

$PythonCmd = $null
foreach ($candidate in @("python", "python3")) {
    $ver = & $candidate --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $PythonCmd = $candidate
        Write-Ok "Python gefunden: $candidate ($ver)"
        break
    }
}

if (-not $PythonCmd) {
    Write-Err "Python nicht gefunden. Bitte python oder python3 installieren."
    exit 1
}

# ---------------------------------------------------------------------------
# Schritt 5 — elmt_to_stencil.py ausfuehren (.elmt -> source/)
# ---------------------------------------------------------------------------

$elmtScript = Join-Path $ForkDir "tools\elmt_to_stencil.py"

if (-not (Test-Path $elmtScript)) {
    Write-Err "Tool nicht gefunden: $elmtScript"
    exit 1
}

Write-Info "Konvertiere .elmt -> Stencil-XML nach source/ ..."
& $PythonCmd $elmtScript $qetElementsDir $sourceDir

if ($LASTEXITCODE -ne 0) {
    Write-Err "elmt_to_stencil.py fehlgeschlagen (Exit $LASTEXITCODE)."
    exit 1
}

Write-Ok "Konvertierung abgeschlossen -> $sourceDir"

# ---------------------------------------------------------------------------
# Schritt 6 — build_library.py ausfuehren (source/ -> output/)
# ---------------------------------------------------------------------------

$buildScript = Join-Path $ForkDir "tools\build_library.py"

if (-not (Test-Path $buildScript)) {
    Write-Err "Tool nicht gefunden: $buildScript"
    exit 1
}

$libOut     = Join-Path $outputDir "IEC_Electrical.xml"
$stencilOut = Join-Path $outputDir "IEC_Stencils.xml"

Write-Info "Baue draw.io-Bibliothek..."
& $PythonCmd $buildScript $sourceDir $libOut --stencils $stencilOut

if ($LASTEXITCODE -ne 0) {
    Write-Err "build_library.py fehlgeschlagen (Exit $LASTEXITCODE)."
    exit 1
}

# ---------------------------------------------------------------------------
# Schritt 7 — Erfolgsmeldung
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host "  IEC-Bibliothek erfolgreich erstellt" -ForegroundColor Cyan
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host ""
Write-Ok "Library  : $libOut"
Write-Ok "Stencils : $stencilOut"
Write-Host ""
Write-Host "  In draw.io laden:" -ForegroundColor Cyan
Write-Host "  Extras -> Bibliothek bearbeiten -> Aus Datei oeffnen -> $libOut" -ForegroundColor White
Write-Host ""
