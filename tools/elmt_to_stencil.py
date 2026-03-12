#!/usr/bin/env python3
"""
elmt_to_stencil.py

Konvertiert QElectroTech .elmt-Symboldateien in draw.io Stencil-XML.
Ausgabe: eine lesbares <shape>-XML pro .elmt-Datei (kein Komprimieren hier).

Verwendung:
    python elmt_to_stencil.py <input_dir> <output_dir>

Beispiel:
    python elmt_to_stencil.py qelectrotech-elements/220 source/iec_60617

Quellen:
    QET-Elemente : https://github.com/qelectrotech/qelectrotech-elements
    Stencil-Spec : https://jgraph.github.io/mxgraph/docs/stencils.pdf
"""

import xml.etree.ElementTree as ET
import math
import os
import glob
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def get_name(defn: ET.Element, lang: str = "de") -> str:
    """Symbolname aus <names> extrahieren; bevorzugt 'lang', Fallback: 'en', dann erste."""
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
    """QET-Style-String parsen: 'line-style:normal;filling:none;color:black' → dict."""
    result = {}
    for part in (style_str or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            result[k.strip()] = v.strip()
    return result


def arc_to_svg_endpoint(x, y, w, h, start_deg, angle_deg, ox, oy):
    """
    QET-Bogen (Bounding-Box + Start/Sweep-Winkel) → SVG-Endpunkt-Parameter.

    QET-Koordinaten: Hotspot = Ursprung, Y nach unten positiv.
    Winkel: 0° = rechts (3 Uhr), positiv = mathematisch positiv (gegen Uhrzeigersinn im
    QET-Math-Koordinatensystem = im Uhrzeigersinn auf dem Bildschirm, weil Y nach unten).

    Rückgabe: (x1, y1, x2, y2, rx, ry, large_arc_flag, sweep_flag)
    """
    bx = x + ox          # Bounding-Box links oben in draw.io-Koordinaten
    by = y + oy
    rx = w / 2.0
    ry = h / 2.0
    cx = bx + rx         # Mittelpunkt
    cy = by + ry

    # Startpunkt auf der Ellipse
    start_rad = math.radians(start_deg)
    x1 = cx + rx * math.cos(start_rad)
    y1 = cy - ry * math.sin(start_rad)   # Y invertiert (Bildschirm-Y nach unten)

    # Endpunkt
    end_rad = math.radians(start_deg + angle_deg)
    x2 = cx + rx * math.cos(end_rad)
    y2 = cy - ry * math.sin(end_rad)

    large_arc = 1 if abs(angle_deg) > 180 else 0
    # QET positiver Winkel = gegen Uhrzeigersinn (Mathe) = im Uhrzeigersinn auf Bildschirm
    sweep = 0 if angle_deg > 0 else 1

    return x1, y1, x2, y2, rx, ry, large_arc, sweep


def fill_cmd(style_dict: dict) -> str:
    """draw.io Füll-/Strich-Befehl aus QET-Style ermitteln."""
    filling = style_dict.get("filling", "none")
    return "<fillstroke/>" if filling != "none" else "<stroke/>"


# ---------------------------------------------------------------------------
# Kern-Konverter: .elmt → <shape>-XML
# ---------------------------------------------------------------------------

def elmt_to_shape_xml(defn: ET.Element, name: str) -> str:
    """
    <definition>-Element aus einer .elmt-Datei → draw.io <shape>-XML (als String).
    Das Ergebnis ist menschenlesbar und kann direkt als Quelldatei eingecheckt werden.
    """
    w   = int(defn.get("width",     40))
    h   = int(defn.get("height",    40))
    ox  = int(defn.get("hotspot_x", w // 2))   # Offset Hotspot → draw.io-Ursprung oben-links
    oy  = int(defn.get("hotspot_y", h // 2))

    fg_lines = []       # <foreground>-Inhalt
    conn_lines = []     # <connections>-Inhalt

    desc = defn.find("description") or defn

    for elem in desc:
        tag = elem.tag

        # --- Linie -------------------------------------------------------
        if tag == "line":
            x1 = float(elem.get("x1", 0)) + ox
            y1 = float(elem.get("y1", 0)) + oy
            x2 = float(elem.get("x2", 0)) + ox
            y2 = float(elem.get("y2", 0)) + oy
            fg_lines.append(
                f'    <path><move x="{x1:.1f}" y="{y1:.1f}"/>'
                f'<line x="{x2:.1f}" y="{y2:.1f}"/></path><stroke/>'
            )

        # --- Rechteck ----------------------------------------------------
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

        # --- Bogen / Ellipse ---------------------------------------------
        elif tag == "arc":
            ax    = float(elem.get("x",      0))
            ay    = float(elem.get("y",      0))
            aw    = float(elem.get("width",  10))
            ah    = float(elem.get("height", 10))
            start = float(elem.get("start",   0))
            angle = float(elem.get("angle", 360))

            if abs(angle) >= 360:
                # Volle Ellipse
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

        # --- Klemme (Anschlusspunkt) -------------------------------------
        elif tag == "terminal":
            tx   = float(elem.get("x", 0)) + ox
            ty   = float(elem.get("y", 0)) + oy
            tname = elem.get("name", "")
            # Normiert auf 0..1 relativ zur Shape-Größe
            cx_frac = round(tx / w, 4) if w > 0 else 0.5
            cy_frac = round(ty / h, 4) if h > 0 else 0.5
            conn_lines.append(
                f'    <constraint name="{tname}" '
                f'x="{cx_frac}" y="{cy_frac}" perimeter="0"/>'
            )

        # dynamic_text, kindInformations, uuid → nicht für Geometrie relevant

    # --- XML zusammenbauen -----------------------------------------------
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
# Datei-Verarbeitung
# ---------------------------------------------------------------------------

def convert_file(elmt_path: str, output_path: str, lang: str = "de") -> bool:
    """Eine .elmt-Datei → eine Stencil-XML-Datei konvertieren."""
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
            f'<!-- Quelle: {os.path.basename(elmt_path)} -->\n'
            f'<!-- Generiert von elmt_to_stencil.py -->\n'
        )
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header + shape_xml + "\n")
        return True
    except Exception as e:
        print(f"  FEHLER {elmt_path}: {e}", file=sys.stderr)
        return False


def convert_directory(input_dir: str, output_dir: str, lang: str = "de"):
    """Alle .elmt-Dateien in input_dir rekursiv konvertieren; Verzeichnisstruktur spiegeln."""
    elmt_files = sorted(glob.glob(
        os.path.join(input_dir, "**", "*.elmt"), recursive=True
    ))
    if not elmt_files:
        print(f"Keine .elmt-Dateien gefunden in: {input_dir}")
        return

    print(f"Konvertiere {len(elmt_files)} Symbole von '{input_dir}' → '{output_dir}'")
    ok = err = 0
    for src in elmt_files:
        # Ausgabepfad: Verzeichnisstruktur relativ zu input_dir spiegeln
        rel = os.path.relpath(src, input_dir)
        dst = os.path.join(output_dir, Path(rel).with_suffix(".xml"))
        if convert_file(src, dst, lang):
            print(f"  OK   {rel}")
            ok += 1
        else:
            err += 1

    print(f"\n{ok} OK, {err} Fehler  →  {output_dir}")


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    convert_directory(sys.argv[1], sys.argv[2], lang="de")
