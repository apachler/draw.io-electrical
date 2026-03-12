#!/usr/bin/env python3
"""
render_preview.py

Renders a grid SVG preview of IEC electrical stencil symbols.

Usage:
    python tools/render_preview.py [build-src-dir] [output.svg]

Defaults:
    build-src-dir : <repo>/build-src
    output.svg    : <repo>/screenshots/symbols_iec.svg
"""

import xml.etree.ElementTree as ET
import glob
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

CELL      = 70      # px per grid cell
PAD       = 10      # inner padding
COLS      = 16      # symbols per row
LABEL_H   = 14      # label row below symbol

STROKE_C  = "#1a1a1a"
BG        = "#ffffff"
FONT      = "monospace"
FONT_SZ   = 7

# Categories to sample (path suffix -> label, max items)
CATEGORIES = [
    ("10_allpole/110_network_supplies",           "Network supplies",      6),
    ("10_allpole/114_connections",                "Connections",           6),
    ("10_allpole/120_cables_wiring",              "Cables / Wiring",       6),
    ("10_allpole/130_terminals_terminal_strips",  "Terminals",             6),
    ("10_allpole/140_connectors_plugs",           "Connectors",            6),
    ("10_allpole/200_fuses_protective_gears",     "Fuses / Protection",    8),
    ("10_allpole/310_relays_contactors_contacts", "Relays / Contacts",     10),
    ("10_allpole/330_transformers_power_supplies","Transformers",          6),
    ("10_allpole/340_converters_inverters",       "Converters",            6),
    ("10_allpole/380_signaling_operating",        "Signaling / Operating", 8),
    ("10_allpole/390_sensors_instruments",        "Sensors",               8),
    ("10_allpole/391_consumers_actuators",        "Actuators",             8),
    ("10_allpole/392_generators_sources",         "Generators",            6),
    ("10_allpole/395_electronics_semiconductors", "Electronics",           10),
    ("10_allpole/450_high_voltage",               "High Voltage",          6),
    ("10_allpole/500_home_installation",          "Home Installation",     6),
    ("91_en_60617/en_60617_02",                   "IEC 60617-02",          8),
    ("91_en_60617/en_60617_03",                   "IEC 60617-03",          8),
    ("91_en_60617/en_60617_07",                   "IEC 60617-07",          8),
    ("91_en_60617/en_60617_08",                   "IEC 60617-08",          8),
]


# ---------------------------------------------------------------------------
# Stencil -> SVG conversion
# ---------------------------------------------------------------------------

PAINT_TAGS = {"stroke", "fillstroke", "fill"}


def _path_d(path_elem, sx, sy, dx, dy):
    parts = []
    for cmd in path_elem:
        t = cmd.tag
        if t == "move":
            x = float(cmd.get("x", 0)) * sx + dx
            y = float(cmd.get("y", 0)) * sy + dy
            parts.append(f"M {x:.2f} {y:.2f}")
        elif t == "line":
            x = float(cmd.get("x", 0)) * sx + dx
            y = float(cmd.get("y", 0)) * sy + dy
            parts.append(f"L {x:.2f} {y:.2f}")
        elif t == "arc":
            rx  = float(cmd.get("rx", 0)) * sx
            ry  = float(cmd.get("ry", 0)) * sy
            xr  = cmd.get("x-rotation", "0")
            la  = cmd.get("large-arc-flag", "0")
            sw  = cmd.get("sweep-flag", "1")
            x   = float(cmd.get("x", 0)) * sx + dx
            y   = float(cmd.get("y", 0)) * sy + dy
            parts.append(f"A {rx:.2f} {ry:.2f} {xr} {la} {sw} {x:.2f} {y:.2f}")
        elif t == "close":
            parts.append("Z")
    return " ".join(parts)


def shape_to_svg_elements(shape_elem, cell_x, cell_y):
    """Convert a draw.io <shape> to SVG element strings, placed at (cell_x, cell_y)."""
    w  = float(shape_elem.get("w", 40))
    h  = float(shape_elem.get("h", 40))

    usable = CELL - 2 * PAD
    scale  = min(usable / w, usable / h)

    # Center within cell
    dx = cell_x + PAD + (usable - w * scale) / 2
    dy = cell_y + PAD + (usable - h * scale) / 2

    sx, sy = scale, scale

    fg = shape_elem.find("foreground")
    if fg is None:
        return []

    children = list(fg)
    out = []
    i = 0
    while i < len(children):
        elem = children[i]
        tag  = elem.tag

        # Look ahead for paint command
        paint = "stroke"
        skip  = 0
        if i + 1 < len(children) and children[i + 1].tag in PAINT_TAGS:
            paint = children[i + 1].tag
            skip  = 1

        fill_v   = "none"   if paint == "stroke"     else STROKE_C
        stroke_v = STROKE_C if paint in ("stroke", "fillstroke") else "none"
        common   = f'fill="{fill_v}" stroke="{stroke_v}" stroke-width="1.2"'

        if tag == "path":
            d = _path_d(elem, sx, sy, dx, dy)
            if d:
                out.append(f'<path d="{d}" {common}/>')
            i += 1 + skip

        elif tag == "rect":
            x  = float(elem.get("x", 0)) * sx + dx
            y  = float(elem.get("y", 0)) * sy + dy
            rw = float(elem.get("w", 10)) * sx
            rh = float(elem.get("h", 10)) * sy
            out.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{rw:.2f}" height="{rh:.2f}" {common}/>')
            i += 1 + skip

        elif tag == "ellipse":
            ex  = float(elem.get("x", 0)) * sx + dx
            ey  = float(elem.get("y", 0)) * sy + dy
            ew  = float(elem.get("w", 10)) * sx
            eh  = float(elem.get("h", 10)) * sy
            cx  = ex + ew / 2
            cy  = ey + eh / 2
            out.append(f'<ellipse cx="{cx:.2f}" cy="{cy:.2f}" rx="{ew/2:.2f}" ry="{eh/2:.2f}" {common}/>')
            i += 1 + skip

        else:
            i += 1

    return out


# ---------------------------------------------------------------------------
# Symbol loading
# ---------------------------------------------------------------------------

def load_shapes(src_dir, category_path, max_count):
    full = os.path.join(src_dir, category_path)
    if not os.path.isdir(full):
        return []
    files = sorted(glob.glob(os.path.join(full, "**", "*.xml"), recursive=True))[:max_count]
    shapes = []
    for f in files:
        try:
            root = ET.parse(f).getroot()
            if root.tag != "shape":
                root = root.find("shape")
            if root is not None:
                shapes.append((root.get("name", Path(f).stem), root))
        except Exception:
            pass
    return shapes


# ---------------------------------------------------------------------------
# Grid renderer
# ---------------------------------------------------------------------------

def render_grid(sections, output_path):
    """
    sections : list of (label, [(name, shape_elem), ...])
    """
    lines = []
    y     = 0

    def emit(s):
        lines.append(s)

    # First pass: compute total height
    total_h = 0
    for label, symbols in sections:
        total_h += LABEL_H + 4          # section header
        rows = max(1, (len(symbols) + COLS - 1) // COLS)
        total_h += rows * (CELL + LABEL_H)
        total_h += 10                   # section gap

    total_w = COLS * CELL

    emit(f'<svg xmlns="http://www.w3.org/2000/svg" '
         f'width="{total_w}" height="{total_h}" '
         f'style="background:{BG}; font-family:{FONT};">')

    y = 4
    for label, symbols in sections:
        # Section header
        emit(f'<text x="4" y="{y + LABEL_H - 2}" '
             f'font-size="10" font-weight="bold" fill="#444">{label}</text>')
        y += LABEL_H + 4

        for idx, (name, shape_elem) in enumerate(symbols):
            col = idx % COLS
            row = idx // COLS
            cx  = col * CELL
            cy  = y + row * (CELL + LABEL_H)

            # Cell background + border
            emit(f'<rect x="{cx}" y="{cy}" width="{CELL}" height="{CELL}" '
                 f'fill="#f8f8f8" stroke="#e0e0e0" stroke-width="0.5"/>')

            # Symbol geometry
            for svg_el in shape_to_svg_elements(shape_elem, cx, cy):
                emit(f'  {svg_el}')

            # Label below cell
            label_y = cy + CELL + LABEL_H - 2
            short   = name[:14] + ".." if len(name) > 14 else name
            emit(f'<text x="{cx + CELL//2}" y="{label_y}" '
                 f'text-anchor="middle" font-size="{FONT_SZ}" fill="#666">{short}</text>')

        rows = max(1, (len(symbols) + COLS - 1) // COLS)
        y += rows * (CELL + LABEL_H) + 10

    emit('</svg>')
    return "\n".join(lines), total_w, total_h


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    script_dir = Path(__file__).parent
    repo_root  = script_dir.parent

    src_dir    = sys.argv[1] if len(sys.argv) > 1 else str(repo_root / "build-src")
    output     = sys.argv[2] if len(sys.argv) > 2 else str(repo_root / "screenshots" / "symbols_iec.svg")

    os.makedirs(os.path.dirname(output), exist_ok=True)

    sections = []
    total    = 0
    for cat_path, cat_label, max_n in CATEGORIES:
        shapes = load_shapes(src_dir, cat_path, max_n)
        if shapes:
            sections.append((cat_label, shapes))
            total += len(shapes)
        else:
            print(f"  SKIP  {cat_path} (not found)", file=sys.stderr)

    print(f"Rendering {total} symbols across {len(sections)} categories...")

    svg, w, h = render_grid(sections, output)
    with open(output, "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"  -> {output}  ({w}x{h}px)")


if __name__ == "__main__":
    main()
