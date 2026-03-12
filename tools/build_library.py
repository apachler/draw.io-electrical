#!/usr/bin/env python3
"""
build_library.py

Compiles draw.io stencil XML source files (from elmt_to_stencil.py) into an
importable draw.io library file (.xml in mxlibrary format).

Usage:
    python build_library.py <source_dir> <output.xml> [--stencils <stencils.xml>]

Arguments:
    source_dir      Directory with stencil XML source files (recursive)
    output.xml      Output library for draw.io (Extras -> Edit Library)
    --stencils      Optional: additionally output a combined <shapes> stencil file

Examples:
    python build_library.py source/ output/IEC_Electrical.xml
    python build_library.py source/ output/IEC_Electrical.xml --stencils output/IEC_Stencils.xml

draw.io import:
    Extras -> Edit Library -> File: output/IEC_Electrical.xml
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
# draw.io compression
# ---------------------------------------------------------------------------

def compress_drawio(text: str) -> str:
    """
    Compress string with raw deflate + base64-encode (draw.io format).
    draw.io uses zlib without header/checksum (wbits=-15).
    """
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    compressed = c.compress(text.encode("utf-8")) + c.flush()
    return base64.b64encode(compressed).decode("utf-8")


# ---------------------------------------------------------------------------
# Stencil XML -> draw.io library entry
# ---------------------------------------------------------------------------

def shape_to_library_entry(shape_elem: ET.Element, source_file: str) -> dict:
    """
    A <shape> element -> dict for the mxlibrary JSON array.

    The <shape> XML is embedded as a stencil in the mxCell style:
        style="shape=stencil(COMPRESSED_SHAPE_XML);..."
    """
    name   = shape_elem.get("name", Path(source_file).stem)
    w      = int(shape_elem.get("w", 40))
    h      = int(shape_elem.get("h", 40))
    aspect = shape_elem.get("aspect", "fixed")

    # Serialize and compress shape XML
    stencil_xml       = ET.tostring(shape_elem, encoding="unicode")
    compressed_stencil = compress_drawio(stencil_xml)

    # Build mxGraphModel with mxCell
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
# Load stencil source files
# ---------------------------------------------------------------------------

def load_shapes_from_dir(source_dir: str) -> list:
    """
    Load all <shape> XML files from source_dir (recursively).
    Returns a sorted list of (name, shape_elem, source_file) tuples.
    """
    xml_files = sorted(glob.glob(
        os.path.join(source_dir, "**", "*.xml"), recursive=True
    ))
    shapes = []
    for path in xml_files:
        try:
            tree = ET.parse(path)
            root = tree.getroot()

            # Supports both standalone <shape> and <shapes> container
            if root.tag == "shape":
                shapes.append((root.get("name", Path(path).stem), root, path))
            elif root.tag == "shapes":
                for shape in root.findall("shape"):
                    shapes.append((shape.get("name", Path(path).stem), shape, path))
            else:
                print(f"  SKIP {path}: unknown root element <{root.tag}>",
                      file=sys.stderr)
        except Exception as e:
            print(f"  ERROR {path}: {e}", file=sys.stderr)

    return shapes


# ---------------------------------------------------------------------------
# Build functions
# ---------------------------------------------------------------------------

def build_mxlibrary(shapes: list, output_path: str):
    """
    Stencil shapes -> importable draw.io library (mxlibrary format).
    """
    entries = []
    for name, shape_elem, src in shapes:
        try:
            entry = shape_to_library_entry(shape_elem, src)
            entries.append(entry)
            print(f"  OK   {name}  ({os.path.basename(src)})")
        except Exception as e:
            print(f"  ERROR {src}: {e}", file=sys.stderr)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("<mxlibrary>")
        f.write(json.dumps(entries, ensure_ascii=False))
        f.write("</mxlibrary>")

    print(f"\n{len(entries)} symbols -> {output_path}")


def build_combined_stencils(shapes: list, output_path: str, library_name: str = "IEC_Electrical"):
    """
    Stencil shapes -> combined <shapes> XML file (importable directly in draw.io
    via Extras -> Edit Stencils).
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

    print(f"{len(shapes)} shapes -> {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Builds a draw.io library from stencil XML source files."
    )
    parser.add_argument("source_dir",  help="Directory with stencil XML source files")
    parser.add_argument("output_xml",  help="Output path for the draw.io library (.xml)")
    parser.add_argument(
        "--stencils",
        metavar="FILE",
        help="Optional: output a combined <shapes> stencil file",
    )
    parser.add_argument(
        "--name",
        default="IEC_Electrical",
        help="Library name (default: IEC_Electrical)",
    )
    args = parser.parse_args()

    print(f"Loading stencils from '{args.source_dir}'...")
    shapes = load_shapes_from_dir(args.source_dir)
    if not shapes:
        print("No <shape> files found.")
        sys.exit(1)

    print(f"{len(shapes)} shapes found.\n")
    print(f"Building mxlibrary: {args.output_xml}")
    build_mxlibrary(shapes, args.output_xml)

    if args.stencils:
        print(f"\nBuilding combined stencil file: {args.stencils}")
        build_combined_stencils(shapes, args.stencils, library_name=args.name)


if __name__ == "__main__":
    main()
