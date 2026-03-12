#!/usr/bin/env python3
"""
build_library.py

Kompiliert draw.io Stencil-XML-Quelldateien (aus elmt_to_stencil.py) zu einer
importierbaren draw.io-Bibliotheksdatei (.xml im mxlibrary-Format).

Verwendung:
    python build_library.py <source_dir> <output.xml> [--stencils <stencils.xml>]

Argumente:
    source_dir      Verzeichnis mit Stencil-XML-Quelldateien (rekursiv)
    output.xml      Ausgabe-Bibliothek fuer draw.io (Extras → Bibliothek bearbeiten)
    --stencils      Optional: zusaetzlich kombinierte <shapes>-Stencil-Datei ausgeben

Beispiele:
    python build_library.py source/ output/IEC_Electrical.xml
    python build_library.py source/ output/IEC_Electrical.xml --stencils output/IEC_Stencils.xml

draw.io-Import:
    Extras → Bibliothek bearbeiten → Datei: output/IEC_Electrical.xml
"""

import xml.etree.ElementTree as ET
import zlib
import base64
import json
import os
import glob
import sys
import argparse
from pathlib import Path


# ---------------------------------------------------------------------------
# draw.io-Komprimierung
# ---------------------------------------------------------------------------

def compress_drawio(text: str) -> str:
    """
    String mit Raw-Deflate komprimieren + Base64-kodieren (draw.io-Format).
    draw.io verwendet zlib ohne Header/Checksum (wbits=-15).
    """
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    compressed = c.compress(text.encode("utf-8")) + c.flush()
    return base64.b64encode(compressed).decode("utf-8")


# ---------------------------------------------------------------------------
# Stencil-XML → draw.io-Bibliotheks-Eintrag
# ---------------------------------------------------------------------------

def shape_to_library_entry(shape_elem: ET.Element, source_file: str) -> dict:
    """
    Ein <shape>-Element → dict fuer das mxlibrary-JSON-Array.

    Das <shape>-XML wird als Stencil in den mxCell-Style eingebettet:
        style="shape=stencil(COMPRESSED_SHAPE_XML);..."
    """
    name   = shape_elem.get("name", Path(source_file).stem)
    w      = int(shape_elem.get("w", 40))
    h      = int(shape_elem.get("h", 40))
    aspect = shape_elem.get("aspect", "fixed")

    # Shape-XML serialisieren und komprimieren
    stencil_xml       = ET.tostring(shape_elem, encoding="unicode")
    compressed_stencil = compress_drawio(stencil_xml)

    # mxGraphModel mit mxCell aufbauen
    mx_xml = (
        "<mxGraphModel>"
        "<root>"
        '<mxCell id="0"/>'
        '<mxCell id="1" parent="0"/>'
        f'<mxCell id="2" value="" '
        f'style="shape=stencil({compressed_stencil});whiteSpace=wrap;html=1;" '
        f'vertex="1" parent="1">'
        f'<mxGeometry width="{w}" height="{h}" as="geometry"/>'
        "</mxCell>"
        "</root>"
        "</mxGraphModel>"
    )
    compressed_mx = compress_drawio(mx_xml)

    return {
        "xml":    compressed_mx,
        "w":      w,
        "h":      h,
        "aspect": aspect,
        "title":  name,
    }


# ---------------------------------------------------------------------------
# Stencil-Quelldateien einlesen
# ---------------------------------------------------------------------------

def load_shapes_from_dir(source_dir: str) -> list:
    """
    Alle <shape>-XML-Dateien aus source_dir (rekursiv) laden.
    Gibt sortierte Liste von (name, shape_elem, source_file)-Tupeln zurueck.
    """
    xml_files = sorted(glob.glob(
        os.path.join(source_dir, "**", "*.xml"), recursive=True
    ))
    shapes = []
    for path in xml_files:
        try:
            tree = ET.parse(path)
            root = tree.getroot()

            # Unterstuetzt sowohl einzelne <shape> als auch <shapes>-Container
            if root.tag == "shape":
                shapes.append((root.get("name", Path(path).stem), root, path))
            elif root.tag == "shapes":
                for shape in root.findall("shape"):
                    shapes.append((shape.get("name", Path(path).stem), shape, path))
            else:
                print(f"  SKIP {path}: unbekanntes Root-Element <{root.tag}>",
                      file=sys.stderr)
        except Exception as e:
            print(f"  FEHLER {path}: {e}", file=sys.stderr)

    return shapes


# ---------------------------------------------------------------------------
# Build-Funktionen
# ---------------------------------------------------------------------------

def build_mxlibrary(shapes: list, output_path: str):
    """
    Stencil-Shapes → importierbare draw.io-Bibliothek (mxlibrary-Format).
    """
    entries = []
    for name, shape_elem, src in shapes:
        try:
            entry = shape_to_library_entry(shape_elem, src)
            entries.append(entry)
            print(f"  OK   {name}  ({os.path.basename(src)})")
        except Exception as e:
            print(f"  FEHLER {src}: {e}", file=sys.stderr)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("<mxlibrary>")
        f.write(json.dumps(entries, ensure_ascii=False))
        f.write("</mxlibrary>")

    print(f"\n{len(entries)} Symbole → {output_path}")


def build_combined_stencils(shapes: list, output_path: str, library_name: str = "IEC_Electrical"):
    """
    Stencil-Shapes → kombinierte <shapes>-XML-Datei (direkt in draw.io importierbar
    ueber Extras → Stencils bearbeiten).
    """
    root = ET.Element("shapes", name=f"mxgraph.{library_name.lower()}")
    for _name, shape_elem, _src in shapes:
        root.append(shape_elem)

    ET.indent(root, space="  ")
    tree = ET.ElementTree(root)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="utf-8", xml_declaration=False)

    print(f"{len(shapes)} Shapes → {output_path}")


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Baut draw.io-Bibliothek aus Stencil-XML-Quelldateien."
    )
    parser.add_argument("source_dir",  help="Verzeichnis mit Stencil-XML-Quelldateien")
    parser.add_argument("output_xml",  help="Ausgabepfad der draw.io-Bibliothek (.xml)")
    parser.add_argument(
        "--stencils",
        metavar="FILE",
        help="Optional: kombinierte <shapes>-Stencil-Datei ausgeben",
    )
    parser.add_argument(
        "--name",
        default="IEC_Electrical",
        help="Bibliotheksname (Standard: IEC_Electrical)",
    )
    args = parser.parse_args()

    print(f"Lade Stencils aus '{args.source_dir}'...")
    shapes = load_shapes_from_dir(args.source_dir)
    if not shapes:
        print("Keine <shape>-Dateien gefunden.")
        sys.exit(1)

    print(f"{len(shapes)} Shapes gefunden.\n")
    print(f"Baue mxlibrary: {args.output_xml}")
    build_mxlibrary(shapes, args.output_xml)

    if args.stencils:
        print(f"\nBaue kombinierte Stencil-Datei: {args.stencils}")
        build_combined_stencils(shapes, args.stencils, library_name=args.name)


if __name__ == "__main__":
    main()
