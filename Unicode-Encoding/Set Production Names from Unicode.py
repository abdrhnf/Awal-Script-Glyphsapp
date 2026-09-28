# MenuTitle: Set Production Names from Unicode
# -*- coding: utf-8 -*-
__doc__ = """
Set productionName for each glyph based on its primary Unicode.
Example:
- beh-ar (0628)      -> productionName: uni0628
- beh-ar.medi (FE92) -> productionName: uniFE92
Glyph name (g.name) is NOT changed.
Glyphs without Unicode will be skipped.

Author: Abdurrahman Hanif — Awal Studio
Version: 1.0
Date: December 2025
"""

from GlyphsApp import *

font = Glyphs.font
if not font:
    Message(
        title="No Font Open",
        message="Please open a font in Glyphs before running this script.",
        OKButton="OK",
    )
else:
    # if there is a selection, use it, otherwise: all
    if font.selectedLayers:
        glyphs_to_process = {l.parent for l in font.selectedLayers}
    else:
        glyphs_to_process = list(font.glyphs)

    font.disableUpdateInterface()

    changed = 0
    skipped = 0

    for g in glyphs_to_process:
        # use primary unicode
        uni = g.unicode

        # if using multiple unicodes and primary is empty, take the first one
        if not uni and getattr(g, "unicodes", None):
            if g.unicodes:
                uni = g.unicodes[0]

        if not uni:
            skipped += 1
            continue

        try:
            uni_int = int(uni, 16)
            # Adobe-style format for BMP: uniXXXX
            if uni_int <= 0xFFFF:
                new_prod = "uni%04X" % uni_int
            else:
                # if someday outside BMP, use uXXXXX
                new_prod = "u%X" % uni_int

            if g.productionName != new_prod:
                print(f"{g.name}: {g.productionName} -> {new_prod}")
                g.productionName = new_prod
                changed += 1
        except Exception as e:
            print(f"[ERROR] {g.name} (unicode {uni}): {e}")
            skipped += 1

    font.enableUpdateInterface()

    print("===== SUMMARY =====")
    print("Production name changed :", changed, "glyphs.")
    print("Skipped (no unicode / error):", skipped, "glyphs.")
