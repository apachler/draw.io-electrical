# draw.io-electrical

IEC electrical schematic symbols for draw.io/diagrams.net, converted from the
[QElectroTech elements library](https://github.com/qelectrotech/qelectrotech-elements).

![Symbols Preview](screenshots/symbols_iec.svg)

## Import

### IEC library (converted from QElectroTech)

1. Download `IEC_Electrical.xml` from this repository.
2. In draw.io: **File → Open Library from → This Device** → select `IEC_Electrical.xml`.

### Original hand-crafted library

`Custom_Electrical.xml` is a smaller, manually created symbol set included in this repo. Import it the same way if you prefer it or want both libraries loaded at once.

![Custom Library Symbols](screenshots/symbols_custom.svg)

## Building from source

Requires Python 3 and MSYS2/Git Bash (or Linux/macOS).

After cloning, initialize the submodule:

```bash
git submodule update --init --recursive
```

Then build:

```bash
bash tools/build_iec_library.sh
```

Outputs `IEC_Electrical.xml` and `IEC_Stencils.xml` in the repo root.

## Regenerating symbol previews

After rebuilding the libraries, regenerate the preview images with:

```bash
# IEC library preview  ->  screenshots/symbols_iec.svg
python tools/render_preview.py

# Hand-crafted library preview  ->  screenshots/symbols_custom.svg
python tools/render_custom_preview.py
```
