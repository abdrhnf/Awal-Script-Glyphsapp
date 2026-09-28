#MenuTitle: Assign Kerning Classes
# -*- coding: utf-8 -*-
__doc__ = """
Assign left and right kerning groups for Latin glyphs.

Rules:
- Simple / suffixed glyph (A, A.sc, A.alt)  → left = right = A
- Ligature with one letter (braceleft_A.liga) → left = right = A  (letter wins)
- Ligature with multiple letters (f_f_i)      → left = f, right = i
- Glyphs with actual components use the same
  letter-priority logic based on component positions.

Glyphs without a Unicode-mapped base are skipped unless
"Override existing groups" is checked, in which case the
name-parsed result is used as-is.

Author: Abdurrahman Hanif — Awal Studio
Version: 1.0
"""

import re
from vanilla import Window, CheckBox, Button, TextBox, HorizontalLine, RadioGroup
from AppKit import NSFloatingWindowLevel


# ── helpers ────────────────────────────────────────────────────────────────

def strip_suffix(name):
    """A.sc → A   |   f_i.liga → f_i   |   braceleft_A.liga → braceleft_A"""
    return name.split(".")[0]


def is_letter(glyph_name, font):
    """True if the glyph exists and its category is Letter."""
    g = font.glyphs[glyph_name]
    if g:
        return (g.category or "").lower() == "letter"
    # Fallback for components not in the font
    base = strip_suffix(glyph_name)
    return bool(re.match(r'^[A-Za-z]$', base))


def resolve_groups(glyph, font):
    """
    Return (left_group, right_group) for a glyph.
    Priority: actual layer components > name parsing.
    """
    master_id = font.selectedFontMaster.id if font.selectedFontMaster else None
    layer = glyph.layers[master_id] if master_id else None
    if layer is None:
        # Sparse layer under the active master (or no active master) — fall
        # back to layer 0 rather than crash.
        layer = glyph.layers[0]

    # ── 1. Use actual components if present ──────────────────────────────
    if layer.components:
        comps = sorted(layer.components, key=lambda c: c.position.x)
        comp_names = [strip_suffix(c.componentName) for c in comps]
        letter_names = [n for n in comp_names if is_letter(n, font)]

        if not letter_names:
            return comp_names[0], comp_names[-1]
        if len(letter_names) == 1:
            return letter_names[0], letter_names[0]
        return letter_names[0], letter_names[-1]

    # ── 2. Name-based parsing ─────────────────────────────────────────────
    base = strip_suffix(glyph.name)

    if "_" in base:
        parts = [strip_suffix(p) for p in base.split("_")]
        letter_parts = [p for p in parts if is_letter(p, font)]

        if not letter_parts:
            return parts[0], parts[-1]
        if len(letter_parts) == 1:
            return letter_parts[0], letter_parts[0]
        return letter_parts[0], letter_parts[-1]

    # Simple glyph — use base name as-is
    return base, base


# ── main tool ───────────────────────────────────────────────────────────────

class AssignKerningClassesTool:
    def __init__(self, font):
        self.font = font
        self._build_ui()

    def _build_ui(self):
        has_selection = bool(self.font.selectedLayers)
        W = 280
        self.w = Window((W, 210), "Assign Kerning Classes", closable=True)
        y = 16

        self.w.scopeLabel = TextBox((16, y, -16, 17), "Scope", sizeStyle="small")
        y += 20
        self.w.scope = RadioGroup(
            (16, y, -16, 44),
            ["All glyphs", "Selected glyphs only"],
            isVertical=True
        )
        self.w.scope.set(1 if has_selection else 0)
        y += 52

        self.w.div = HorizontalLine((16, y, -16, 1))
        y += 14

        self.w.cb_skip = CheckBox(
            (16, y, -16, 20),
            "Skip glyphs that already have groups",
            value=True
        )
        y += 34

        self.w.cancelBtn = Button((16, y, 80, 24),   "Cancel", callback=self._cancel)
        self.w.runBtn    = Button((-108, y, 92, 24), "Assign", callback=self._run)

        self.w.open()
        self.w.center()
        self.w._window.setLevel_(NSFloatingWindowLevel)

    def _cancel(self, sender):
        self.w.close()

    def _run(self, sender):
        skip_existing = bool(self.w.cb_skip.get())
        scope_idx     = self.w.scope.get()
        self.w.close()
        self._process(skip_existing, scope_idx)

    def _process(self, skip_existing, scope_idx):
        font = self.font

        if scope_idx == 1 and font.selectedLayers:
            glyphs = list({l.parent for l in font.selectedLayers})
        else:
            glyphs = list(font.glyphs)

        assigned = []
        skipped  = []
        unchanged = []

        font.disableUpdateInterface()
        try:
            for g in glyphs:
                has_left  = bool(g.leftKerningGroup)
                has_right = bool(g.rightKerningGroup)

                if skip_existing and (has_left or has_right):
                    skipped.append(g.name)
                    continue

                left, right = resolve_groups(g, font)

                changed = False
                if g.leftKerningGroup != left:
                    g.leftKerningGroup = left
                    changed = True
                if g.rightKerningGroup != right:
                    g.rightKerningGroup = right
                    changed = True

                if changed:
                    assigned.append(f"{g.name:<28} L={left}  R={right}")
                else:
                    unchanged.append(g.name)
        finally:
            font.enableUpdateInterface()

        # ── summary ──────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("ASSIGN KERNING CLASSES — DONE")
        print("=" * 60)

        if assigned:
            print(f"\n✅ Assigned ({len(assigned)}):")
            for line in assigned:
                print(f"   {line}")

        if skipped:
            print(f"\n⏭  Skipped — already had groups ({len(skipped)}):")
            for name in skipped[:20]:
                print(f"   {name}")
            if len(skipped) > 20:
                print(f"   … and {len(skipped)-20} more")

        if unchanged:
            print(f"\n— Unchanged (groups already matched): {len(unchanged)}")

        print("\n" + "=" * 60)

        msg = f"Assigned {len(assigned)} glyph(s)."
        if skipped:
            msg += f"  {len(skipped)} skipped (had groups)."
        Glyphs.showNotification("Assign Kerning Classes", msg)


# ── entry point ─────────────────────────────────────────────────────────────

font = Glyphs.font
if not font:
    print("No font open.")
else:
    AssignKerningClassesTool(font)
