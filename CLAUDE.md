# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo does

Converts QElectroTech `.elmt` symbol files (from the `qelectrotech-elements` git submodule) into a
draw.io-importable library. The pipeline runs in two stages:

1. **`.elmt` → stencil XML** (`elmt_to_stencil.py`) — one human-readable `<shape>` XML file per
   `.elmt` file, mirroring the source directory structure into `build-src/`.
2. **stencil XML → draw.io library** (`build_library.py`) — compresses each shape with raw-deflate +
   base64 (draw.io's own format) and writes one mxlibrary file per category into
   `libraries/categorized/` plus matching `<shapes>` stencil files into
   `libraries/categorized/stencils/`. With `--combined` it also writes the single-file bundle into
   `libraries/combined/`.

Only the `10_electric` subtree of the submodule is converted (IEC electrical symbols only).

## Building

```bash
bash tools/build_iec_library.sh                    # per-category output (default)
bash tools/build_iec_library.sh --combined         # also build combined single-file library
bash tools/build_iec_library.sh /other             # explicit repo root override
bash tools/build_iec_library.sh /other --combined
```

Default outputs in `libraries/`:
- `categorized/IEC Electrical - *.xml` — one mxlibrary file per category
- `categorized/stencils/IEC Electrical - *.xml` — matching `<shapes>` stencil files
- `mcp_context.md` — shape name reference for AI/MCP use

With `--combined`, also writes:
- `combined/IEC_Electrical.xml` — single mxlibrary with all symbols
- `combined/IEC_Stencils.xml` — single combined `<shapes>` file

Intermediate stencil sources land in `build-src/` (gitignored).

### First-time setup — submodule

The submodule is already registered in `.gitmodules`. After cloning, just run:

```bash
git submodule update --init --recursive
```

The build script runs this automatically when `qelectrotech-elements/10_electric/` is missing or empty.

## mcp_context.md — always regenerate after builds

`libraries/mcp_context.md` is **auto-generated** by `build_library.py --split` and must never
be edited by hand. It is regenerated on every normal build run (step 6 of
`build_iec_library.sh`).

**Claude Code rule:** If any file under `libraries/categorized/`, `libraries/combined/`, or
`build-src/` is added, modified, or removed, `libraries/mcp_context.md` MUST be rebuilt by
running:

    bash tools/build_iec_library.sh

Do not commit changes to `libraries/` without also committing the regenerated
`libraries/mcp_context.md` from the same build run.

## Running the Python tools directly

```bash
# Stage 1 only
python tools/elmt_to_stencil.py qelectrotech-elements/10_electric build-src

# Stage 2 only — per-category (default)
python tools/build_library.py build-src --split libraries

# Stage 2 only — single combined file
python tools/build_library.py build-src libraries/combined/IEC_Electrical.xml --stencils libraries/combined/IEC_Stencils.xml
```

## Regenerating preview images

```bash
# IEC library (from build-src/) -> screenshots/symbols_iec.svg
python tools/render_preview.py

# Hand-crafted library (from Custom_Electrical.xml) -> screenshots/symbols_custom.svg
python tools/render_custom_preview.py
```

`render_preview.py` samples symbols from `build-src/` by category. Edit the `CATEGORIES` list at
the top to change which categories appear and how many symbols each shows.

`render_custom_preview.py` decodes the mxlibrary format (URL-decode → zlib → URL-decode → zlib)
to recover each `<shape>` element before rendering.

## Key implementation details

- **draw.io compression** (`build_library.py:compress_drawio`) uses `zlib` with `wbits=-15` (raw
  deflate, no header/checksum) followed by base64. This is draw.io's own stencil encoding — standard
  zlib will not work.
- **mxlibrary format** (`Custom_Electrical.xml`): each entry's `xml` field is URL-encoded +
  compressed mxGraphModel XML. The mxCell style contains `shape=stencil(...)` where the value is
  another URL-encoded + compressed `<shape>` element. `render_custom_preview.py` reverses this.
- **Coordinate system** (`elmt_to_stencil.py`): QET uses a hotspot origin; the converter shifts all
  coordinates by `(hotspot_x, hotspot_y)` to produce draw.io's top-left origin. Arc angles follow
  math convention (0° = right, positive = CCW) but screen Y is inverted, so `sweep-flag` logic is
  inverted accordingly.
- **Stencil XML format**: children of `<foreground>` follow a painter's model — a shape element
  (`<path>`, `<rect>`, `<ellipse>`) is always followed by a sibling paint command (`<stroke/>`,
  `<fillstroke/>`, or `<fill/>`). Parsers must look-ahead one sibling to determine fill/stroke.
  `<path>` children are `<move>`, `<line>`, `<arc>`, `<close>` — mapping directly to SVG `M`, `L`,
  `A`, `Z`. `<rect>`/`<ellipse>` use `x`, `y`, `w`, `h` attributes (not SVG's `width`/`height`).
- **Print statements** in all Python scripts must use ASCII-only characters — the Windows console
  codepage (cp1252) cannot encode Unicode arrows (`→`). Use `->` instead.
- **Python requirement**: 3.x only (no third-party dependencies).
