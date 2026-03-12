#!/usr/bin/env python3
"""
render_custom_preview.py

Renders a preview SVG of all symbols in Custom_Electrical.xml (mxlibrary format).

Usage:
    python tools/render_custom_preview.py [Custom_Electrical.xml] [output.svg]

Defaults:
    input  : <repo>/Custom_Electrical.xml
    output : <repo>/screenshots/symbols_custom.svg
"""

import base64
import json
import re
import sys
import zlib
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

CELL      = 80
PAD       = 12
COLS      = 10
LABEL_H   = 14

STROKE_C  = "#1a1a1a"
BG        = "#ffffff"
FONT      = "monospace"
FONT_SZ   = 8

# ---------------------------------------------------------------------------
# draw.io decompression
# ---------------------------------------------------------------------------

def decompress_drawio(b64: str) -> str:
    return unquote(zlib.decompress(base64.b64decode(b64), -15).decode("utf-8"))


def extract_shape_xml(library_entry: dict) -> ET.Element | None:
    """Decompress mxlibrary entry -> <shape> element."""
    try:
        mx_xml   = decompress_drawio(library_entry["xml"])
        mx_root  = ET.fromstring(mx_xml)
        cell     = mx_root.find(".//mxCell[@vertex='1']")
        if cell is None:
            return None
        style = cell.get("style", "")
        m = re.search(r"shape=stencil\(([^)]+)\)", style)
        if not m:
            return None
        shape_xml = decompress_drawio(m.group(1))
        return ET.fromstring(shape_xml)
    except Exception as e:
        print(f"  WARN: {library_entry.get('title','?')} — {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Stencil -> SVG (same painter's model as render_preview.py)
# ---------------------------------------------------------------------------

PAINT_TAGS = {"stroke", "fillstroke", "fill"}


def _path_d(path_elem, sx, sy, dx, dy):
    parts = []
    for cmd in path_elem:
        t = cmd.tag
        if t == "move":
            parts.append(f"M {float(cmd.get('x',0))*sx+dx:.2f} {float(cmd.get('y',0))*sy+dy:.2f}")
        elif t == "line":
            parts.append(f"L {float(cmd.get('x',0))*sx+dx:.2f} {float(cmd.get('y',0))*sy+dy:.2f}")
        elif t == "arc":
            rx = float(cmd.get("rx", 0)) * sx
            ry = float(cmd.get("ry", 0)) * sy
            x  = float(cmd.get("x",  0)) * sx + dx
            y  = float(cmd.get("y",  0)) * sy + dy
            parts.append(
                f"A {rx:.2f} {ry:.2f} {cmd.get('x-rotation','0')} "
                f"{cmd.get('large-arc-flag','0')} {cmd.get('sweep-flag','1')} "
                f"{x:.2f} {y:.2f}"
            )
        elif t == "close":
            parts.append("Z")
    return " ".join(parts)


def shape_to_svg_elements(shape_elem, cell_x, cell_y):
    w = float(shape_elem.get("w", 40))
    h = float(shape_elem.get("h", 40))
    usable = CELL - 2 * PAD
    scale  = min(usable / w, usable / h)
    dx = cell_x + PAD + (usable - w * scale) / 2
    dy = cell_y + PAD + (usable - h * scale) / 2
    sx = sy = scale

    fg = shape_elem.find("foreground")
    if fg is None:
        return []

    children = list(fg)
    out = []
    i = 0
    while i < len(children):
        elem  = children[i]
        tag   = elem.tag
        paint = "stroke"
        skip  = 0
        if i + 1 < len(children) and children[i + 1].tag in PAINT_TAGS:
            paint = children[i + 1].tag
            skip  = 1

        fill_v   = "none"    if paint == "stroke"              else STROKE_C
        stroke_v = STROKE_C  if paint in ("stroke","fillstroke") else "none"
        common   = f'fill="{fill_v}" stroke="{stroke_v}" stroke-width="1.5"'

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
            ex = float(elem.get("x", 0)) * sx + dx
            ey = float(elem.get("y", 0)) * sy + dy
            ew = float(elem.get("w", 10)) * sx
            eh = float(elem.get("h", 10)) * sy
            out.append(
                f'<ellipse cx="{ex+ew/2:.2f}" cy="{ey+eh/2:.2f}" '
                f'rx="{ew/2:.2f}" ry="{eh/2:.2f}" {common}/>'
            )
            i += 1 + skip
        else:
            i += 1

    return out


# ---------------------------------------------------------------------------
# Grid renderer
# ---------------------------------------------------------------------------

def render_grid(symbols, output_path):
    rows  = (len(symbols) + COLS - 1) // COLS
    total_w = COLS * CELL
    total_h = rows * (CELL + LABEL_H) + 8

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{total_w}" height="{total_h}" '
        f'style="background:{BG}; font-family:{FONT};">'
    ]

    for idx, (name, shape_elem) in enumerate(symbols):
        col = idx % COLS
        row = idx // COLS
        cx  = col * CELL
        cy  = row * (CELL + LABEL_H) + 4

        lines.append(
            f'<rect x="{cx}" y="{cy}" width="{CELL}" height="{CELL}" '
            f'fill="#f8f8f8" stroke="#e0e0e0" stroke-width="0.5"/>'
        )
        for el in shape_to_svg_elements(shape_elem, cx, cy):
            lines.append(f'  {el}')

        short   = name[:10] + ".." if len(name) > 10 else name
        label_y = cy + CELL + LABEL_H - 2
        lines.append(
            f'<text x="{cx + CELL//2}" y="{label_y}" '
            f'text-anchor="middle" font-size="{FONT_SZ}" fill="#555">{short}</text>'
        )

    lines.append('</svg>')
    return "\n".join(lines), total_w, total_h


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    repo_root = Path(__file__).parent.parent
    input_xml = sys.argv[1] if len(sys.argv) > 1 else str(repo_root / "Custom_Electrical.xml")
    output    = sys.argv[2] if len(sys.argv) > 2 else str(repo_root / "screenshots" / "symbols_custom.svg")

    with open(input_xml, encoding="utf-8") as f:
        raw = f.read()

    json_str = raw.removeprefix("<mxlibrary>").removesuffix("</mxlibrary>")
    entries  = json.loads(json_str)

    symbols = []
    for entry in entries:
        shape = extract_shape_xml(entry)
        if shape is not None:
            symbols.append((entry.get("title", "?"), shape))

    print(f"Rendering {len(symbols)} symbols from {input_xml}...")

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    svg, w, h = render_grid(symbols, output)
    with open(output, "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"  -> {output}  ({w}x{h}px)")


if __name__ == "__main__":
    main()
