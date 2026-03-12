#!/usr/bin/env python3
"""
build_library.py

Compiles draw.io stencil XML source files (from elmt_to_stencil.py) into an
importable draw.io library file (.xml in mxlibrary format).

Usage:
    python build_library.py <source_dir> --split <outdir>
    python build_library.py <source_dir> <output.xml> [--stencils <stencils.xml>]

Arguments:
    source_dir      Directory with stencil XML source files (recursive)
    --split OUTDIR  Write one mxlibrary file per category into OUTDIR (default mode)
    output.xml      Output path for a single combined library (optional)
    --stencils      Optional: additionally output a combined <shapes> stencil file

Examples:
    python build_library.py source/ --split libraries/
    python build_library.py source/ output/IEC_Electrical.xml
    python build_library.py source/ output/IEC_Electrical.xml --stencils output/IEC_Stencils.xml

draw.io import:
    File -> Open Library from -> This Device -> select .xml file
"""

import xml.etree.ElementTree as ET
import zlib
import base64
import json
import os
import glob
import sys
import argparse
from collections import Counter
from pathlib import Path


# ---------------------------------------------------------------------------
# Category mapping: build-src-relative path -> display name
# ---------------------------------------------------------------------------

CATEGORY_MAP = {
    "10_allpole/100_folio_referencing":          "Folio References",
    "10_allpole/110_network_supplies":            "Network Supplies",
    "10_allpole/114_connections":                 "Connections",
    "10_allpole/120_cables_wiring":               "Cables & Wiring",
    "10_allpole/130_terminals_terminal_strips":   "Terminals",
    "10_allpole/140_connectors_plugs":            "Connectors & Plugs",
    "10_allpole/200_fuses_protective_gears":      "Fuses & Protection",
    "10_allpole/310_relays_contactors_contacts":  "Relays & Contactors",
    "10_allpole/330_transformers_power_supplies": "Transformers",
    "10_allpole/340_converters_inverters":        "Converters",
    "10_allpole/380_signaling_operating":         "Signaling",
    "10_allpole/390_sensors_instruments":         "Sensors & Instruments",
    "10_allpole/391_consumers_actuators":         "Consumers & Actuators",
    "10_allpole/392_generators_sources":          "Sources & Generators",
    "10_allpole/395_electronics_semiconductors":  "Electronics & Semiconductors",
    "10_allpole/450_high_voltage":                "High Voltage",
    "10_allpole/500_home_installation":           "Home Installation",
    "11_singlepole":                              "Single-Pole",
    "91_en_60617":                                "EN 60617",
    "98_graphics":                                "Graphics",
}


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
# Deduplication
# ---------------------------------------------------------------------------

def _deduplicate_names(shapes: list) -> list:
    """
    Ensure all shape names in the list are unique.
    For colliding names, appends " (filename_stem)" to disambiguate.
    Falls back to " (parent/stem)" if the stem-based name still collides.
    Mutates each shape_elem's name attribute to match the unique name.
    Shapes must be in a stable sorted order (guaranteed by load_shapes_from_dir).
    Returns a new list of (unique_name, shape_elem, src) tuples.
    """
    name_count = Counter(name for name, _, _ in shapes)
    seen = set()
    result = []
    for name, elem, src in shapes:
        if name_count[name] == 1:
            unique = name
        else:
            stem = Path(src).stem
            candidate = f"{name} ({stem})"
            if candidate in seen:
                parent = Path(src).parent.name
                candidate = f"{name} ({parent}/{stem})"
            unique = candidate
        seen.add(unique)
        elem.set("name", unique)
        result.append((unique, elem, src))
    return result


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
# Split-by-category build
# ---------------------------------------------------------------------------

def _display_name_to_ns(display_name: str) -> str:
    """Convert a display name to a stencil namespace suffix."""
    return display_name.lower().replace(" & ", "_").replace(" ", "_")


def build_split_libraries(shapes: list, source_dir: str, out_dir: str):
    """
    For each category in CATEGORY_MAP, write into out_dir:
      - categorized/IEC Electrical - {name}.xml          mxlibrary panel file
      - categorized/stencils/IEC Electrical - {name}.xml  <shapes> stencil file

    Also writes mcp_context.md (at out_dir root) listing all shape names by category
    for use as AI/MCP context.
    """
    source_dir_norm = os.path.normpath(source_dir)
    categorized_dir = os.path.join(out_dir, "categorized")
    stencils_dir = os.path.join(categorized_dir, "stencils")
    os.makedirs(categorized_dir, exist_ok=True)
    os.makedirs(stencils_dir, exist_ok=True)

    total_files = 0
    context_sections = []

    for rel_path, display_name in CATEGORY_MAP.items():
        category_prefix = os.path.normpath(
            os.path.join(source_dir_norm, rel_path)
        ) + os.sep

        category_shapes = [
            (name, elem, src)
            for name, elem, src in shapes
            if os.path.normpath(src).startswith(category_prefix)
        ]

        if not category_shapes:
            continue

        category_shapes = _deduplicate_names(category_shapes)

        filename = f"IEC Electrical - {display_name}.xml"

        # --- mxlibrary panel file ---
        entries = []
        for name, shape_elem, src in category_shapes:
            try:
                entries.append(shape_to_library_entry(shape_elem, src))
            except Exception as e:
                print(f"  ERROR {src}: {e}", file=sys.stderr)

        with open(os.path.join(categorized_dir, filename), "w", encoding="utf-8") as f:
            f.write("<mxlibrary>")
            f.write(json.dumps(entries, ensure_ascii=False))
            f.write("</mxlibrary>")

        # --- stencil <shapes> file ---
        ns = f"mxgraph.iec_electrical.{_display_name_to_ns(display_name)}"
        shapes_root = ET.Element("shapes", name=ns)
        for _name, shape_elem, _src in category_shapes:
            shapes_root.append(shape_elem)
        ET.indent(shapes_root, space="  ")
        stencil_tree = ET.ElementTree(shapes_root)
        with open(os.path.join(stencils_dir, filename), "wb") as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            stencil_tree.write(f, encoding="utf-8", xml_declaration=False)

        # --- accumulate context section ---
        names = [name for name, _elem, _src in category_shapes]
        context_sections.append((display_name, filename, ns, names))

        print(f"  [OK]  {filename}  ({len(entries)} shapes)")
        total_files += 1

    # --- mcp_context.md ---
    context_path = os.path.join(out_dir, "mcp_context.md")
    with open(context_path, "w", encoding="utf-8") as f:
        f.write("# IEC Electrical Stencil Shape Names\n\n")
        f.write("Register the stencil files from `libraries/categorized/stencils/` in draw.io via\n")
        f.write("**Extras -> Edit Stencils**, then reference shapes in cell styles as:\n\n")
        f.write("    shape=stencil(NAME)\n\n")
        f.write("where NAME is one of the values listed below.\n\n")
        for display_name, filename, ns, names in context_sections:
            f.write(f"## {display_name}\n\n")
            f.write(f"Stencil file: `libraries/categorized/stencils/{filename}`  \n")
            f.write(f"Namespace: `{ns}`\n\n")
            for name in names:
                f.write(f"- `{name}`\n")
            f.write("\n")
    print(f"  [OK]  mcp_context.md")

    print(f"\n{total_files} category files -> {out_dir}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Builds a draw.io library from stencil XML source files."
    )
    parser.add_argument("source_dir", help="Directory with stencil XML source files")
    parser.add_argument(
        "output_xml",
        nargs="?",
        help="Output path for the draw.io library (.xml); omit when using --split",
    )
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
    parser.add_argument(
        "--split",
        metavar="OUTDIR",
        help="Write one mxlibrary per category into OUTDIR instead of a single file",
    )
    args = parser.parse_args()

    if not args.split and not args.output_xml:
        parser.error("output_xml is required unless --split is given")

    print(f"Loading stencils from '{args.source_dir}'...")
    shapes = load_shapes_from_dir(args.source_dir)
    if not shapes:
        print("No <shape> files found.")
        sys.exit(1)

    print(f"{len(shapes)} shapes found.\n")

    if args.split:
        print(f"Building per-category libraries in '{args.split}'...")
        build_split_libraries(shapes, args.source_dir, args.split)
    else:
        shapes = _deduplicate_names(shapes)
        print(f"Building mxlibrary: {args.output_xml}")
        build_mxlibrary(shapes, args.output_xml)

        if args.stencils:
            print(f"\nBuilding combined stencil file: {args.stencils}")
            build_combined_stencils(shapes, args.stencils, library_name=args.name)


if __name__ == "__main__":
    main()
