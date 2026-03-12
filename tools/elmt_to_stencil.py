#!/usr/bin/env python3
"""
elmt_to_stencil.py

Converts QElectroTech .elmt symbol files to draw.io stencil XML.
Output: one human-readable <shape> XML per .elmt file (no compression here).

Usage:
    python elmt_to_stencil.py <input_dir> <output_dir>

Example:
    python elmt_to_stencil.py qelectrotech-elements/220 source/iec_60617

Sources:
    QET elements : https://github.com/qelectrotech/qelectrotech-elements
    Stencil spec : https://jgraph.github.io/mxgraph/docs/stencils.pdf
"""

import xml.etree.ElementTree as ET
import math
import os
import glob
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_name(defn: ET.Element, lang: str = "en") -> str:
    """Extract symbol name from <names>; prefers 'lang', fallback: 'en', then first."""
    names = defn.find("names")
    if names is None:
        return Path(defn.get("file", "unknown")).stem
    for l in (lang, "en"):
        el = names.find(f"name[@lang='{l}']")
        if el is not None and el.text:
            return el.text.strip()
    first = names.find("name")
    return first.text.strip() if first is not None and first.text else "unknown"


def parse_style(style_str: str) -> dict:
    """Parse QET style string: 'line-style:normal;filling:none;color:black' → dict."""
    result = {}
    for part in (style_str or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            result[k.strip()] = v.strip()
    return result


def arc_to_svg_endpoint(x, y, w, h, start_deg, angle_deg, ox, oy):
    """
    QET arc (bounding box + start/sweep angle) → SVG endpoint parameters.

    QET coordinates: hotspot = origin, Y positive downward.
    Angle: 0° = right (3 o'clock), positive = math-positive (counter-clockwise in
    QET math coords = clockwise on screen because Y is down).

    Returns: (x1, y1, x2, y2, rx, ry, large_arc_flag, sweep_flag)
    """
    bx = x + ox          # Bounding box top-left in draw.io coordinates
    by = y + oy
    rx = w / 2.0
    ry = h / 2.0
    cx = bx + rx         # Mittelpunkt
    cy = by + ry

    # Start point on the ellipse
    start_rad = math.radians(start_deg)
    x1 = cx + rx * math.cos(start_rad)
    y1 = cy - ry * math.sin(start_rad)   # Y inverted (screen Y is down)

    # End point
    end_rad = math.radians(start_deg + angle_deg)
    x2 = cx + rx * math.cos(end_rad)
    y2 = cy - ry * math.sin(end_rad)

    large_arc = 1 if abs(angle_deg) > 180 else 0
    # QET positive angle = counter-clockwise (math) = clockwise on screen
    sweep = 0 if angle_deg > 0 else 1

    return x1, y1, x2, y2, rx, ry, large_arc, sweep


def fill_cmd(style_dict: dict) -> str:
    """Determine draw.io fill/stroke command from QET style."""
    filling = style_dict.get("filling", "none")
    return "<fillstroke/>" if filling != "none" else "<stroke/>"


# ---------------------------------------------------------------------------
# Core converter: .elmt → <shape> XML
# ---------------------------------------------------------------------------

def elmt_to_shape_xml(defn: ET.Element, name: str) -> str:
    """
    <definition> element from a .elmt file → draw.io <shape> XML (as string).
    The result is human-readable and can be checked in directly as a source file.
    """
    w   = int(defn.get("width",     40))
    h   = int(defn.get("height",    40))
    ox  = int(defn.get("hotspot_x", w // 2))   # Offset hotspot → draw.io origin top-left
    oy  = int(defn.get("hotspot_y", h // 2))

    fg_lines = []       # <foreground> content
    conn_lines = []     # <connections> content

    desc = defn.find("description") or defn

    for elem in desc:
        tag = elem.tag

        # --- Line --------------------------------------------------------
        if tag == "line":
            x1 = float(elem.get("x1", 0)) + ox
            y1 = float(elem.get("y1", 0)) + oy
            x2 = float(elem.get("x2", 0)) + ox
            y2 = float(elem.get("y2", 0)) + oy
            fg_lines.append(
                f'    <path><move x="{x1:.1f}" y="{y1:.1f}"/>'
                f'<line x="{x2:.1f}" y="{y2:.1f}"/></path><stroke/>'
            )

        # --- Rectangle ---------------------------------------------------
        elif tag == "rect":
            rx  = float(elem.get("x",      0)) + ox
            ry  = float(elem.get("y",      0)) + oy
            rw  = float(elem.get("width",  10))
            rh  = float(elem.get("height", 10))
            st  = parse_style(elem.get("style", ""))
            fg_lines.append(
                f'    <rect x="{rx:.1f}" y="{ry:.1f}" w="{rw:.1f}" h="{rh:.1f}"/>'
                f'{fill_cmd(st)}'
            )

        # --- Arc / Ellipse -----------------------------------------------
        elif tag == "arc":
            ax    = float(elem.get("x",      0))
            ay    = float(elem.get("y",      0))
            aw    = float(elem.get("width",  10))
            ah    = float(elem.get("height", 10))
            start = float(elem.get("start",   0))
            angle = float(elem.get("angle", 360))

            if abs(angle) >= 360:
                # Full ellipse
                ex = ax + ox
                ey = ay + oy
                fg_lines.append(
                    f'    <ellipse x="{ex:.1f}" y="{ey:.1f}" w="{aw:.1f}" h="{ah:.1f}"/>'
                    f'<stroke/>'
                )
            else:
                x1, y1, x2, y2, erx, ery, la, sw = arc_to_svg_endpoint(
                    ax, ay, aw, ah, start, angle, ox, oy
                )
                fg_lines.append(
                    f'    <path>'
                    f'<move x="{x1:.1f}" y="{y1:.1f}"/>'
                    f'<arc rx="{erx:.1f}" ry="{ery:.1f}" x-rotation="0" '
                    f'large-arc-flag="{la}" sweep-flag="{sw}" '
                    f'x="{x2:.1f}" y="{y2:.1f}"/>'
                    f'</path><stroke/>'
                )

        # --- Polygon -----------------------------------------------------
        elif tag == "polygon":
            points = []
            i = 1
            while elem.get(f"x{i}") is not None:
                px = float(elem.get(f"x{i}")) + ox
                py = float(elem.get(f"y{i}")) + oy
                points.append((px, py))
                i += 1
            if len(points) >= 2:
                closed = elem.get("closed", "true").lower() == "true"
                st = parse_style(elem.get("style", ""))
                cmds = [f'<move x="{points[0][0]:.1f}" y="{points[0][1]:.1f}"/>']
                for px, py in points[1:]:
                    cmds.append(f'<line x="{px:.1f}" y="{py:.1f}"/>')
                if closed:
                    cmds.append("<close/>")
                fg_lines.append(
                    f'    <path>{"".join(cmds)}</path>{fill_cmd(st)}'
                )

        # --- Terminal (connection point) ---------------------------------
        elif tag == "terminal":
            tx   = float(elem.get("x", 0)) + ox
            ty   = float(elem.get("y", 0)) + oy
            tname = elem.get("name", "")
            # Normalized to 0..1 relative to shape size
            cx_frac = round(tx / w, 4) if w > 0 else 0.5
            cy_frac = round(ty / h, 4) if h > 0 else 0.5
            conn_lines.append(
                f'    <constraint name="{tname}" '
                f'x="{cx_frac}" y="{cy_frac}" perimeter="0"/>'
            )

        # dynamic_text, kindInformations, uuid → not relevant for geometry

    # --- Assemble XML ----------------------------------------------------
    lines = [f'<shape name="{name}" w="{w}" h="{h}" aspect="fixed">']

    if conn_lines:
        lines.append("  <connections>")
        lines.extend(conn_lines)
        lines.append("  </connections>")

    lines.append("  <foreground>")
    lines.append('    <strokewidth width="1"/>')
    lines.extend(fg_lines)
    lines.append("  </foreground>")
    lines.append("</shape>")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File processing
# ---------------------------------------------------------------------------

def convert_file(elmt_path: str, output_path: str, lang: str = "en") -> bool:
    """Convert one .elmt file → one stencil XML file."""
    try:
        tree = ET.parse(elmt_path)
        root = tree.getroot()
        defn = root if root.tag == "definition" else root.find("definition")
        if defn is None:
            defn = root

        name = get_name(defn, lang)
        shape_xml = elmt_to_shape_xml(defn, name)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        header = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<!-- Source: {os.path.basename(elmt_path)} -->\n'
            f'<!-- Generated by elmt_to_stencil.py -->\n'
        )
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header + shape_xml + "\n")
        return True
    except Exception as e:
        print(f"  ERROR {elmt_path}: {e}", file=sys.stderr)
        return False


def convert_directory(input_dir: str, output_dir: str, lang: str = "en"):
    """Convert all .elmt files in input_dir recursively; mirror directory structure."""
    elmt_files = sorted(glob.glob(
        os.path.join(input_dir, "**", "*.elmt"), recursive=True
    ))
    if not elmt_files:
        print(f"No .elmt files found in: {input_dir}")
        return

    print(f"Converting {len(elmt_files)} symbols from '{input_dir}' -> '{output_dir}'")
    ok = err = 0
    for src in elmt_files:
        # Output path: mirror directory structure relative to input_dir
        rel = os.path.relpath(src, input_dir)
        dst = os.path.join(output_dir, Path(rel).with_suffix(".xml"))
        if convert_file(src, dst, lang):
            print(f"  OK   {rel}")
            ok += 1
        else:
            err += 1

    print(f"\n{ok} OK, {err} errors  ->  {output_dir}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    convert_directory(sys.argv[1], sys.argv[2], lang="en")
