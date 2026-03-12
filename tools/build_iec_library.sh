#!/usr/bin/env bash
# build_iec_library.sh
# Conversion pipeline: qelectrotech-elements -> draw.io library
#
# Usage:
#   bash tools/build_iec_library.sh               # auto-detects repo root
#   bash tools/build_iec_library.sh /path/to/fork # explicit override

set -euo pipefail

# ---------------------------------------------------------------------------
# Color logging (disabled when stdout is not a TTY)
# ---------------------------------------------------------------------------

if [ -t 1 ]; then
    C_GREEN='\033[0;32m'
    C_CYAN='\033[0;36m'
    C_YELLOW='\033[1;33m'
    C_RED='\033[0;31m'
    C_RESET='\033[0m'
else
    C_GREEN='' C_CYAN='' C_YELLOW='' C_RED='' C_RESET=''
fi

log_ok()   { printf "  ${C_GREEN}[OK]${C_RESET}  %s\n" "$1"; }
log_info() { printf "  ${C_CYAN}[..]${C_RESET}  %s\n" "$1"; }
log_warn() { printf "  ${C_YELLOW}[!!]${C_RESET}  %s\n" "$1"; }
log_err()  { printf "  ${C_RED}[ERR]${C_RESET} %s\n" "$1" >&2; }

# ---------------------------------------------------------------------------
# Step 1 — Resolve FORK_DIR
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "${1:-}" != "" ]; then
    FORK_DIR="$1"
else
    FORK_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

if [ ! -d "$FORK_DIR" ]; then
    log_err "Directory not found: $FORK_DIR"
    exit 1
fi

log_info "ForkDir: $FORK_DIR"

# ---------------------------------------------------------------------------
# Step 2 — Check / init qelectrotech-elements submodule
# ---------------------------------------------------------------------------

QET_ELEMENTS_DIR="$FORK_DIR/qelectrotech-elements/10_electric"

if [ ! -d "$QET_ELEMENTS_DIR" ] || [ -z "$(ls -A "$QET_ELEMENTS_DIR" 2>/dev/null)" ]; then
    log_warn "qelectrotech-elements/elements/ not found or empty. Initializing submodule..."

    # Check whether the submodule is registered at all
    if ! git -C "$FORK_DIR" config --file .gitmodules --get-regexp 'submodule\..*\.url' &>/dev/null; then
        log_err "No submodules configured in .gitmodules."
        log_info "Register the submodule first:"
        log_info "  git submodule add https://github.com/qelectrotech/qelectrotech-elements.git qelectrotech-elements"
        log_info "  git submodule update --init --recursive"
        exit 1
    fi

    git -C "$FORK_DIR" submodule update --init --recursive
fi

if ! find "$QET_ELEMENTS_DIR" -name "*.elmt" -print -quit 2>/dev/null | grep -q .; then
    log_err "No .elmt files found in $QET_ELEMENTS_DIR."
    log_info "Manual: git -C '$FORK_DIR' submodule update --init --recursive"
    exit 1
fi

log_ok ".elmt files found in $QET_ELEMENTS_DIR"

# ---------------------------------------------------------------------------
# Step 3 — Create source/ directory
# ---------------------------------------------------------------------------

SOURCE_DIR="$FORK_DIR/build-src"

if [ ! -d "$SOURCE_DIR" ]; then
    mkdir -p "$SOURCE_DIR"
    log_ok "Directory created: $SOURCE_DIR"
fi

# ---------------------------------------------------------------------------
# Step 4 — Detect Python 3
# ---------------------------------------------------------------------------

PYTHON_CMD=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        if "$candidate" -c "import sys; assert sys.version_info[0] == 3" 2>/dev/null; then
            PYTHON_CMD="$candidate"
            PY_VER="$("$candidate" --version 2>&1)"
            log_ok "Python found: $candidate ($PY_VER)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    log_err "Python 3 not found. Please install python3."
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 5 — Run elmt_to_stencil.py (.elmt -> source/)
# ---------------------------------------------------------------------------

ELMT_SCRIPT="$FORK_DIR/tools/elmt_to_stencil.py"

if [ ! -f "$ELMT_SCRIPT" ]; then
    log_err "Tool not found: $ELMT_SCRIPT"
    exit 1
fi

log_info "Converting .elmt -> stencil XML to source/ ..."
"$PYTHON_CMD" "$ELMT_SCRIPT" "$QET_ELEMENTS_DIR" "$SOURCE_DIR"
log_ok "Conversion complete -> $SOURCE_DIR"

# ---------------------------------------------------------------------------
# Step 6 — Run build_library.py (source/ -> repo root)
# ---------------------------------------------------------------------------

BUILD_SCRIPT="$FORK_DIR/tools/build_library.py"

if [ ! -f "$BUILD_SCRIPT" ]; then
    log_err "Tool not found: $BUILD_SCRIPT"
    exit 1
fi

LIB_OUT="$FORK_DIR/IEC_Electrical.xml"
STENCIL_OUT="$FORK_DIR/IEC_Stencils.xml"

log_info "Building draw.io library..."
"$PYTHON_CMD" "$BUILD_SCRIPT" "$SOURCE_DIR" "$LIB_OUT" --stencils "$STENCIL_OUT"

# ---------------------------------------------------------------------------
# Step 7 — Success summary
# ---------------------------------------------------------------------------

printf "\n"
printf "  ${C_CYAN}============================================${C_RESET}\n"
printf "  ${C_CYAN}IEC library built successfully${C_RESET}\n"
printf "  ${C_CYAN}============================================${C_RESET}\n"
printf "\n"
log_ok "Library  : $LIB_OUT"
log_ok "Stencils : $STENCIL_OUT"
printf "\n"
printf "  ${C_CYAN}Load in draw.io:${C_RESET}\n"
printf "  Extras -> Edit Library -> Open from File -> %s\n" "$LIB_OUT"
printf "\n"
