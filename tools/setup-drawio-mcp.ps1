#Requires -Version 5.1
<#
.SYNOPSIS
    Setup-Script: draw.io + MCP-Server + IEC-Symbolbibliothek (Fork-Workflow)

.DESCRIPTION
    Installiert und konfiguriert:
      1.  Node.js LTS                (via Scoop)
      2.  draw.io Desktop            (via Scoop, extras-Bucket)
      3.  @drawio/mcp                (offizieller MCP-Server, via npm)
      4.  .mcp.json                  (MCP-Konfiguration fuer Claude Code)
      5.  Python 3                   (via Scoop, falls fehlend)
      6.  Fork draw.io-electrical    (optional: GitHub-Fork klonen)
      7.  QElectroTech-Elemente      (als Git-Submodul im Fork)
      8.  Python-Tools               (elmt_to_stencil.py + build_library.py in Fork kopieren)
      9.  Initiale Konvertierung     (optional: .elmt -> Stencil-XML)

.NOTES
    Voraussetzungen: Scoop, Git, Claude Code, GitHub-Account
    Ausfuehren:  powershell -ExecutionPolicy Bypass -File tools\setup-drawio-mcp.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

function Write-Step {
    param([int]$Nr, [string]$Text)
    Write-Host ("`n[Schritt $Nr] $Text") -ForegroundColor Cyan
}

function Write-Ok   { param([string]$T); Write-Host "  [OK] $T"   -ForegroundColor Green  }
function Write-Skip { param([string]$T); Write-Host "  [--] $T (bereits vorhanden)" -ForegroundColor Yellow }
function Write-Warn { param([string]$T); Write-Host "  [!!] $T"   -ForegroundColor Yellow }
function Write-Info { param([string]$T); Write-Host "       $T"   -ForegroundColor Gray   }

function Test-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Read-YesNo {
    param([string]$Prompt)
    $answer = Read-Host "  $Prompt [j/n]"
    return $answer.Trim().ToLower() -eq "j"
}

function Copy-ToolFile {
    param([string]$FileName, [string]$TargetDir)
    $src = Join-Path $PSScriptRoot $FileName
    $dst = Join-Path $TargetDir $FileName
    if (Test-Path $src) {
        Copy-Item $src $dst -Force
        Write-Ok "$FileName -> $dst"
    } else {
        Write-Warn "$FileName nicht gefunden in $PSScriptRoot"
    }
}

# ---------------------------------------------------------------------------
# Pfade (Coveris-Projekt)
# ---------------------------------------------------------------------------

$CoverisRoot = Split-Path -Parent $PSScriptRoot
$McpJsonPath = Join-Path $CoverisRoot ".mcp.json"

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "  draw.io IEC-Symbolbibliothek -- Setup" -ForegroundColor Cyan
Write-Host "  ======================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# Schritt 1: Scoop pruefen
# ---------------------------------------------------------------------------

Write-Step 1 "Scoop pruefen"

if (-not (Test-Command "scoop")) {
    Write-Error "Scoop ist nicht installiert.`nInstallation: https://scoop.sh"
}
Write-Ok "Scoop: $(scoop --version 2>&1 | Select-Object -First 1)"

# ---------------------------------------------------------------------------
# Schritt 2: Node.js LTS
# ---------------------------------------------------------------------------

Write-Step 2 "Node.js LTS pruefen / installieren"

if (Test-Command "node") {
    Write-Skip "Node.js $(node --version)"
} else {
    Write-Info "Installiere nodejs-lts via Scoop..."
    scoop install nodejs-lts
    Write-Ok "Node.js $(node --version) installiert"
}
Write-Ok "npm $(npm --version)"

# ---------------------------------------------------------------------------
# Schritt 3: draw.io Desktop
# ---------------------------------------------------------------------------

Write-Step 3 "draw.io Desktop pruefen / installieren"

$buckets = scoop bucket list 2>&1 | Out-String
if ($buckets -notmatch "extras") {
    Write-Info "Scoop extras-Bucket hinzufuegen..."
    scoop bucket add extras
    Write-Ok "extras-Bucket hinzugefuegt"
} else {
    Write-Skip "Scoop extras-Bucket"
}

$scoopList = scoop list 2>&1 | Out-String
if ($scoopList -match "draw\.io") {
    Write-Skip "draw.io Desktop"
} else {
    Write-Info "Installiere draw.io Desktop..."
    scoop install draw.io
    Write-Ok "draw.io Desktop installiert"
}

# ---------------------------------------------------------------------------
# Schritt 4: @drawio/mcp MCP-Server
# ---------------------------------------------------------------------------

Write-Step 4 "@drawio/mcp MCP-Server pruefen / installieren"

$mcpInstalled = npm list -g --depth=0 2>&1 | Out-String
if ($mcpInstalled -match "@drawio/mcp") {
    Write-Skip "@drawio/mcp"
} else {
    Write-Info "Installiere @drawio/mcp global..."
    npm install -g @drawio/mcp
    Write-Ok "@drawio/mcp $(npm show @drawio/mcp version 2>&1) installiert"
}

# ---------------------------------------------------------------------------
# Schritt 5: .mcp.json fuer Claude Code
# ---------------------------------------------------------------------------

Write-Step 5 ".mcp.json konfigurieren"

$drawioMcpEntry = [ordered]@{
    command = "npx"
    args    = @("-y", "@drawio/mcp")
    type    = "stdio"
}

if (Test-Path $McpJsonPath) {
    $existing = Get-Content $McpJsonPath -Raw
    if ($existing -match "@drawio/mcp") {
        Write-Skip ".mcp.json (drawio-Eintrag bereits vorhanden)"
    } else {
        $obj = $existing | ConvertFrom-Json
        $obj.mcpServers | Add-Member -MemberType NoteProperty -Name "drawio" -Value $drawioMcpEntry
        $obj | ConvertTo-Json -Depth 4 | Set-Content $McpJsonPath -Encoding UTF8
        Write-Ok ".mcp.json um drawio-Eintrag erweitert: $McpJsonPath"
    }
} else {
    @{ mcpServers = @{ drawio = $drawioMcpEntry } } |
        ConvertTo-Json -Depth 4 |
        Set-Content $McpJsonPath -Encoding UTF8
    Write-Ok ".mcp.json erstellt: $McpJsonPath"
}

# ---------------------------------------------------------------------------
# Schritt 6: Python 3
# ---------------------------------------------------------------------------

Write-Step 6 "Python 3 pruefen / installieren"

if (Test-Command "python") {
    $pyVer = python --version 2>&1
    Write-Skip "Python $pyVer"
} elseif (Test-Command "python3") {
    $pyVer = python3 --version 2>&1
    Write-Skip "Python3 $pyVer"
} else {
    Write-Info "Installiere Python via Scoop..."
    scoop install python
    Write-Ok "Python $(python --version 2>&1) installiert"
}

# Python-Kommando bestimmen (python oder python3)
$PythonCmd = if (Test-Command "python") { "python" } else { "python3" }
Write-Ok "Python-Kommando: $PythonCmd"

# ---------------------------------------------------------------------------
# Schritt 7: GitHub-Fork klonen (optional)
# ---------------------------------------------------------------------------

Write-Step 7 "Lokalen Fork draw.io-electrical einrichten (optional)"

$ForkDir = $null

if (Read-YesNo "Hast du den Fork bereits lokal geklont?") {
    Write-Host ""
    Write-Info "Tipp: Vorher manuell klonen mit:"
    Write-Info "  git clone https://github.com/DEIN-USER/draw.io-electrical C:\Pfad\draw.io-electrical"
    Write-Host ""
    $inputDir = Read-Host "  Pfad zum lokalen Fork-Verzeichnis"
    $ForkDir  = $inputDir.Trim()

    if (-not (Test-Path (Join-Path $ForkDir ".git"))) {
        Write-Error "Kein Git-Repository gefunden in: $ForkDir`nBitte zuerst manuell klonen."
    }
    Write-Ok "Fork-Verzeichnis: $ForkDir"

    # Verzeichnisstruktur anlegen
    $dirs = @("source", "output", "tools", "qelectrotech-elements")
    foreach ($d in $dirs) {
        $p = Join-Path $ForkDir $d
        if (-not (Test-Path $p)) {
            New-Item -ItemType Directory -Path $p | Out-Null
            Write-Ok "Verzeichnis angelegt: $d\"
        } else {
            Write-Skip "$d\ (existiert)"
        }
    }

    # .gitignore ergaenzen (output/ nicht einchecken ist optional -- hier: einchecken)
    $gitignorePath = Join-Path $ForkDir ".gitignore"
    if (-not (Test-Path $gitignorePath)) {
        @("__pycache__/", "*.pyc", ".DS_Store") | Set-Content $gitignorePath -Encoding UTF8
        Write-Ok ".gitignore erstellt"
    }

} else {
    Write-Warn "Fork-Clone uebersprungen. Schritt 8+9 werden ebenfalls uebersprungen."
    Write-Info "Fuehre das Script erneut aus, sobald der Fork auf GitHub angelegt ist."
}

# ---------------------------------------------------------------------------
# Schritt 8: QElectroTech-Elemente als Submodul + Python-Tools kopieren
# ---------------------------------------------------------------------------

Write-Step 8 "QElectroTech-Elemente & Python-Tools einrichten"

if ($null -eq $ForkDir) {
    Write-Warn "Uebersprungen (kein Fork-Verzeichnis)."
} else {
    # QElectroTech-Elemente als Git-Submodul
    $qetDir = Join-Path $ForkDir "qelectrotech-elements"
    $qetGit = Join-Path $qetDir ".git"

    if (Test-Path $qetGit) {
        Write-Skip "qelectrotech-elements (Submodul bereits vorhanden)"
    } else {
        $qetSubmodulePath = Join-Path $ForkDir ".gitmodules"
        if (Test-Path $qetSubmodulePath) {
            # Submodul-Konfiguration vorhanden, aber nicht initialisiert
            Write-Info "Initialisiere Submodul..."
            git -C $ForkDir submodule update --init --recursive
            Write-Ok "Submodul initialisiert"
        } else {
            Write-Info "Fuege qelectrotech-elements als Submodul hinzu..."
            git -C $ForkDir submodule add `
                https://github.com/qelectrotech/qelectrotech-elements.git `
                qelectrotech-elements
            Write-Ok "Submodul hinzugefuegt: qelectrotech-elements"
        }
    }

    # Python-Tools in Fork kopieren
    Write-Info "Kopiere Python-Tools in Fork..."
    $forkToolsDir = Join-Path $ForkDir "tools"
    Copy-ToolFile "elmt_to_stencil.py"  $forkToolsDir
    Copy-ToolFile "build_library.py"    $forkToolsDir

    # LICENSE (CC BY 4.0) anlegen falls fehlend
    $licensePath = Join-Path $ForkDir "LICENSE"
    if (-not (Test-Path $licensePath)) {
        $year = (Get-Date).Year
        @"
Creative Commons Attribution 4.0 International (CC BY 4.0)

Copyright (c) $year Andreas Pachler
Based on work by bzarek (https://github.com/bzarek/draw.io-electrical)

You are free to:
  Share  -- copy and redistribute the material in any medium or format
  Adapt  -- remix, transform, and build upon the material for any purpose,
            even commercially.

Under the following terms:
  Attribution -- You must give appropriate credit, provide a link to the
                 license, and indicate if changes were made.

Full license text: https://creativecommons.org/licenses/by/4.0/legalcode
"@ | Set-Content $licensePath -Encoding UTF8
        Write-Ok "LICENSE (CC BY 4.0) erstellt"
    } else {
        Write-Skip "LICENSE"
    }

    # NOTICE anlegen falls fehlend
    $noticePath = Join-Path $ForkDir "NOTICE"
    if (-not (Test-Path $noticePath)) {
        @"
NOTICE -- draw.io-electrical IEC Symbol Library

Original work:
  Author : bzarek
  Source : https://github.com/bzarek/draw.io-electrical

Modifications and IEC 60617 symbol additions:
  Author : Andreas Pachler
  Source : https://github.com/DEIN-USER/draw.io-electrical
  Note   : Update this URL after publishing the fork.

IEC symbol reference data sourced from:
  QElectroTech Elements Collection
  https://github.com/qelectrotech/qelectrotech-elements
  License: see individual element files
"@ | Set-Content $noticePath -Encoding UTF8
        Write-Ok "NOTICE erstellt (bitte GitHub-URL aktualisieren)"
        Write-Warn "NOTICE: Eigene GitHub-URL in $noticePath eintragen!"
    } else {
        Write-Skip "NOTICE"
    }
}

# ---------------------------------------------------------------------------
# Schritt 9: Initiale Konvertierung (optional)
# ---------------------------------------------------------------------------

Write-Step 9 "Initiale .elmt → Stencil-XML Konvertierung (optional)"

if ($null -eq $ForkDir) {
    Write-Warn "Uebersprungen (kein Fork-Verzeichnis)."
} else {
    $qetElementsDir = Join-Path $ForkDir "qelectrotech-elements"
    $hasElmt = (Get-ChildItem $qetElementsDir -Filter "*.elmt" -Recurse -ErrorAction SilentlyContinue |
                    Select-Object -First 1) -ne $null

    if (-not $hasElmt) {
        Write-Warn "Keine .elmt-Dateien gefunden. Submodul vollstaendig initialisiert?"
        Write-Info "Manuell: git -C '$ForkDir' submodule update --init"
    } else {
        Write-Info "Submodul bereit. Bibliothek bauen mit:"
        Write-Info "  powershell -ExecutionPolicy Bypass -File tools\build_iec_library.ps1 -ForkDir '$ForkDir'"
    }
}

# ---------------------------------------------------------------------------
# Zusammenfassung
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host "  Setup abgeschlossen" -ForegroundColor Cyan
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Node.js    : $(node --version)"     -ForegroundColor White
Write-Host "  npm        : $(npm --version)"       -ForegroundColor White
Write-Host "  Python     : $(& $PythonCmd --version 2>&1)" -ForegroundColor White
Write-Host "  MCP-Server : @drawio/mcp (npx -y @drawio/mcp)" -ForegroundColor White
Write-Host "  MCP-Config : $McpJsonPath"           -ForegroundColor White
if ($ForkDir) {
    Write-Host "  Fork-Dir   : $ForkDir"           -ForegroundColor White
}
Write-Host ""
Write-Host "  Naechste Schritte:" -ForegroundColor Cyan
Write-Host "  1. Claude Code neu starten"          -ForegroundColor White
Write-Host "  2. /mcp  --> 'drawio' als connected pruefen" -ForegroundColor White
if ($ForkDir) {
    $libFile = Join-Path $ForkDir "output\IEC_Electrical.xml"
    Write-Host "  3. draw.io -> Extras -> Bibliothek bearbeiten -> $libFile" -ForegroundColor White
    Write-Host "  4. NOTICE: eigene GitHub-URL eintragen"  -ForegroundColor White
    Write-Host "  5. git -C '$ForkDir' add . && git commit -m 'Add IEC stencil tools'" -ForegroundColor White
    Write-Host "  6. git -C '$ForkDir' push"               -ForegroundColor White
    Write-Host "  7. Pull Request an bzarek mit CC-BY-4.0-Lizenzvorschlag" -ForegroundColor White
} else {
    Write-Host "  3. Fork auf GitHub anlegen + lokal klonen, dann Script erneut ausfuehren:" -ForegroundColor Yellow
    Write-Host "     git clone https://github.com/DEIN-USER/draw.io-electrical C:\Pfad\draw.io-electrical" -ForegroundColor Gray
}
Write-Host ""

Write-Host "  Workflow (danach laufend):" -ForegroundColor Cyan
Write-Host "  elmt_to_stencil.py  --> source/**/*.xml  (lesbare Stencil-Quellen)" -ForegroundColor Gray
Write-Host "  build_library.py    --> output/IEC_Electrical.xml  (draw.io Import)" -ForegroundColor Gray
Write-Host "  build_library.py --stencils --> output/IEC_Stencils.xml  (alternativ)" -ForegroundColor Gray
Write-Host ""
