#MenuTitle: Assign Unicode…
# -*- coding: utf-8 -*-
"""
Assign Unicode (Arabic-aware, merged)

Replaces the old pair "Assign Missing Unicode.py" + "Auto-Assign Arabic
Unicode.py". Those two scripts wrote to the same field (glyph.unicode) and
were order-dependent: if the generic script ran first, custom Arabic glyphs
(e.g. fatha-ar, lam_alefWasla-ar) got a PUA codepoint before the Arabic
script ever saw them — and since both scripts skip glyphs that already have
a unicode, the Arabic assignment then never happened. Merging into one pass
with a fixed priority order removes that trap entirely.

Resolution order per glyph (first match wins):
  1. Arabic direct-name mapping (marks, lam-alef ligatures, combined marks,
     numbers, punctuation, symbols)
  2. Arabic positional form (.init/.medi/.fina/.isol) resolved against the
     base letter's Unicode via ARABIC_FORMS
  3. Glyphs' built-in glyph-info database (standard Unicode by name)
  4. PUA (E000-F8FF by default), sequential, skipping codepoints already in use

Runs inside Glyphs 3. Place this file in:
  ~/Library/Application Support/Glyphs 3/Scripts/
Scope: processes the current selection if any glyphs are selected,
otherwise all exported glyphs in the font. Skips glyphs that already have
a unicode (idempotent). Preview before apply; full log to Macro Panel.
"""

from AppKit import (
    NSAlert, NSTextField, NSScrollView, NSTextView,
    NSFont, NSColor, NSMakeRect, NSMakeSize,
    NSAlertFirstButtonReturn,
)

PUA_START_DEFAULT = 0xE000
PUA_END           = 0xF8FF


# ============================================================================
# ARABIC BASE LETTERS - Presentation Forms-B
# Format: base_unicode: [isolated, final, initial, medial]
# ============================================================================
ARABIC_FORMS = {
    0x0621: [0xFE80, None, None, None],
    0x0622: [0xFE81, 0xFE82, None, None],
    0x0623: [0xFE83, 0xFE84, None, None],
    0x0624: [0xFE85, 0xFE86, None, None],
    0x0625: [0xFE87, 0xFE88, None, None],
    0x0626: [0xFE89, 0xFE8A, 0xFE8B, 0xFE8C],
    0x0627: [0xFE8D, 0xFE8E, None, None],
    0x0628: [0xFE8F, 0xFE90, 0xFE91, 0xFE92],
    0x0629: [0xFE93, 0xFE94, None, None],
    0x062A: [0xFE95, 0xFE96, 0xFE97, 0xFE98],
    0x062B: [0xFE99, 0xFE9A, 0xFE9B, 0xFE9C],
    0x062C: [0xFE9D, 0xFE9E, 0xFE9F, 0xFEA0],
    0x062D: [0xFEA1, 0xFEA2, 0xFEA3, 0xFEA4],
    0x062E: [0xFEA5, 0xFEA6, 0xFEA7, 0xFEA8],
    0x062F: [0xFEA9, 0xFEAA, None, None],
    0x0630: [0xFEAB, 0xFEAC, None, None],
    0x0631: [0xFEAD, 0xFEAE, None, None],
    0x0632: [0xFEAF, 0xFEB0, None, None],
    0x0633: [0xFEB1, 0xFEB2, 0xFEB3, 0xFEB4],
    0x0634: [0xFEB5, 0xFEB6, 0xFEB7, 0xFEB8],
    0x0635: [0xFEB9, 0xFEBA, 0xFEBB, 0xFEBC],
    0x0636: [0xFEBD, 0xFEBE, 0xFEBF, 0xFEC0],
    0x0637: [0xFEC1, 0xFEC2, 0xFEC3, 0xFEC4],
    0x0638: [0xFEC5, 0xFEC6, 0xFEC7, 0xFEC8],
    0x0639: [0xFEC9, 0xFECA, 0xFECB, 0xFECC],
    0x063A: [0xFECD, 0xFECE, 0xFECF, 0xFED0],
    0x0640: [0x0640, 0x0640, 0x0640, 0x0640],
    0x0641: [0xFED1, 0xFED2, 0xFED3, 0xFED4],
    0x0642: [0xFED5, 0xFED6, 0xFED7, 0xFED8],
    0x0643: [0xFED9, 0xFEDA, 0xFEDB, 0xFEDC],
    0x0644: [0xFEDD, 0xFEDE, 0xFEDF, 0xFEE0],
    0x0645: [0xFEE1, 0xFEE2, 0xFEE3, 0xFEE4],
    0x0646: [0xFEE5, 0xFEE6, 0xFEE7, 0xFEE8],
    0x0647: [0xFEE9, 0xFEEA, 0xFEEB, 0xFEEC],
    0x0648: [0xFEED, 0xFEEE, None, None],
    0x0649: [0xFEEF, 0xFEF0, 0xFBE8, 0xFBE9],
    0x064A: [0xFEF1, 0xFEF2, 0xFEF3, 0xFEF4],
    0x0671: [0xFB50, 0xFB51, None, None],

    # Extended Arabic Letters
    0x067E: [0xFB56, 0xFB57, 0xFB58, 0xFB59],
    0x0679: [0xFB66, 0xFB67, 0xFB68, 0xFB69],
    0x0686: [0xFB7A, 0xFB7B, 0xFB7C, 0xFB7D],
    0x0688: [0xFB88, 0xFB89, None, None],
    0x0691: [0xFB8C, 0xFB8D, None, None],
    0x0698: [0xFB8A, 0xFB8B, None, None],
    0x06A4: [0xFB6A, 0xFB6B, 0xFB6C, 0xFB6D],
    0x06A9: [0xFB8E, 0xFB8F, 0xFB90, 0xFB91],
    0x06AF: [0xFB92, 0xFB93, 0xFB94, 0xFB95],
    0x06BA: [0xFB9E, 0xFB9F, None, None],
    0x06BE: [0xFBAA, 0xFBAB, 0xFBAC, 0xFBAD],
    0x06C0: [0xFBA4, 0xFBA5, None, None],
    0x06C1: [0xFBA6, 0xFBA7, 0xFBA8, 0xFBA9],
    0x06CC: [0xFBFC, 0xFBFD, 0xFBFE, 0xFBFF],
    0x06D2: [0xFBAE, 0xFBAF, None, None],
    0x06D3: [0xFBB0, 0xFBB1, None, None],
}

ARABIC_MARKS = {
    'fatha-ar': 0x064E,
    'damma-ar': 0x064F,
    'kasra-ar': 0x0650,
    'shadda-ar': 0x0651,
    'sukun-ar': 0x0652,

    'fathatan-ar': 0x064B,
    'dammatan-ar': 0x064C,
    'kasratan-ar': 0x064D,

    'maddah-ar': 0x0653,
    'hamzaabove-ar': 0x0654,
    'hamzabelow-ar': 0x0655,
    'alefabove-ar': 0x0670,
    'superscriptalef-ar': 0x0670,

    # Wasla mark — U+FBC2 (ARABIC SYMBOL WASLA ABOVE, added Unicode 14.0)
    # Note: alef wasla letter U+0671 is handled separately in ARABIC_FORMS.
    'wasla-ar': 0xFBC2,
    'smallhighseen-ar': 0x06DC,
    'smallhighroundeedzero-ar': 0x06DF,
    'smallhighuprightedzero-ar': 0x06E0,
    'smallhighmeem-isolatedarorm-ar': 0x06E2,
    'smalllowseen-ar': 0x06E3,
    'smallwaw-ar': 0x06E5,
    'smallyeh-ar': 0x06E6,
    'smallhighnoon-ar': 0x06E8,

    'openfathatan-ar': 0x08F0,
    'opendammatan-ar': 0x08F1,
    'openkasratan-ar': 0x08F2,
}

LAM_ALEF_LIGATURES = {
    'lam_alef-ar': 0xFEFB,
    'lam_alef-ar.fina': 0xFEFC,
    'lam_alef-ar.isol': 0xFEFB,

    'lam_alefHamzaabove-ar': 0xFEF7,
    'lam_alefHamzaabove-ar.fina': 0xFEF8,
    'lam_alefHamzaabove-ar.isol': 0xFEF7,

    'lam_alefHamzabelow-ar': 0xFEF9,
    'lam_alefHamzabelow-ar.fina': 0xFEFA,
    'lam_alefHamzabelow-ar.isol': 0xFEF9,

    'lam_alefMadda-ar': 0xFEF5,
    'lam_alefMadda-ar.fina': 0xFEF6,
    'lam_alefMadda-ar.isol': 0xFEF5,

    'lam_alefWasla-ar': 0xFDF2,
    'lam_alefWasla-ar.fina': 0xFDF2,
    'lam_alefWasla-ar.isol': 0xFDF2,

    'lamAlef-ar': 0xFEFB,
    'lamAlef-ar.fina': 0xFEFC,
    'lamAlef-ar.isol': 0xFEFB,
    'lamAlefHamzaAbove-ar': 0xFEF7,
    'lamAlefHamzaAbove-ar.fina': 0xFEF8,
    'lamAlefHamzaAbove-ar.isol': 0xFEF7,
    'lamAlefHamzaBelow-ar': 0xFEF9,
    'lamAlefHamzaBelow-ar.fina': 0xFEFA,
    'lamAlefHamzaBelow-ar.isol': 0xFEF9,
    'lamAlefMadda-ar': 0xFEF5,
    'lamAlefMadda-ar.fina': 0xFEF6,
    'lamAlefMadda-ar.isol': 0xFEF5,
    'lamAlefWasla-ar': 0xFDF2,
    'lam_alefwasla-ar': 0xFDF2,
}

COMBINED_MARKS = {
    'shaddaFatha-ar': 0xFC60,
    'shaddafatha-ar': 0xFC60,
    'shadda_fatha-ar': 0xFC60,
    'shaddaFatha': 0xFC60,
    'shadda-fatha-ar': 0xFC60,

    'shaddaDamma-ar': 0xFC61,
    'shaddadamma-ar': 0xFC61,
    'shadda_damma-ar': 0xFC61,
    'shaddaDamma': 0xFC61,
    'shadda-damma-ar': 0xFC61,

    'shaddaKasra-ar': 0xFC62,
    'shaddakasra-ar': 0xFC62,
    'shadda_kasra-ar': 0xFC62,
    'shaddaKasra': 0xFC62,
    'shadda-kasra-ar': 0xFC62,

    'shaddaFathatan-ar': 0xFCF2,
    'shaddafathatan-ar': 0xFCF2,
    'shadda_fathatan-ar': 0xFCF2,

    'shaddaDammatan-ar': 0xFCF3,
    'shaddadammatan-ar': 0xFCF3,
    'shadda_dammatan-ar': 0xFCF3,

    'shaddaKasratan-ar': 0xFCF4,
    'shaddakasratan-ar': 0xFCF4,
    'shadda_kasratan-ar': 0xFCF4,
}

ARABIC_NUMBERS = {
    'zero-ar': 0x0660,
    'one-ar': 0x0661,
    'two-ar': 0x0662,
    'three-ar': 0x0663,
    'four-ar': 0x0664,
    'five-ar': 0x0665,
    'six-ar': 0x0666,
    'seven-ar': 0x0667,
    'eight-ar': 0x0668,
    'nine-ar': 0x0669,

    'four-persian': 0x06F4,
    'five-persian': 0x06F5,
    'six-persian': 0x06F6,
    'seven-persian': 0x06F7,
}

ARABIC_PUNCTUATION = {
    'comma-ar': 0x060C,
    'semicolon-ar': 0x061B,
    'question-ar': 0x061F,
    'questionmark-ar': 0x061F,
    'percent-ar': 0x066A,
    'thousandsseparator-ar': 0x066C,
    'decimalseparator-ar': 0x066B,
    'perthousand-ar': 0x060F,
    'star-ar': 0x066D,
}

ARABIC_SYMBOLS = {
    'tatweel-ar': 0x0640,
    'dotlessbeh-ar': 0x066E,
    'dotlessqaf-ar': 0x066F,
    'rub-ar': 0xFDFC,
}

ARABIC_DIRECT_GROUPS = [
    (LAM_ALEF_LIGATURES, "lam-alef"),
    (ARABIC_MARKS, "mark"),
    (COMBINED_MARKS, "combined"),
    (ARABIC_NUMBERS, "number"),
    (ARABIC_PUNCTUATION, "punctuation"),
    (ARABIC_SYMBOLS, "symbol"),
]

POSITIONAL_SUFFIXES = ['.init', '.medi', '.fina', '.isol']
FORM_INDEX_BY_SUFFIX = {None: 0, '.isol': 0, '.fina': 1, '.init': 2, '.medi': 3}


# ---------- Arabic-specific resolution ----------

def arabic_direct_lookup(glyph_name):
    """Return (unicode_int, category) for a direct Arabic name mapping, or None."""
    for mapping, category in ARABIC_DIRECT_GROUPS:
        if glyph_name in mapping:
            return mapping[glyph_name], category
    return None


def strip_positional_suffix(glyph_name):
    """
    Split a positional glyph name into (base_name, suffix). Only strips the
    suffix itself (via slicing, not str.replace) so a suffix-like substring
    elsewhere in the name is never touched.
    """
    for suffix in POSITIONAL_SUFFIXES:
        if glyph_name.endswith(suffix):
            return glyph_name[: -len(suffix)], suffix
    return glyph_name, None


def find_base_unicode(font, base_name):
    """
    Resolve the base Unicode for a (possibly synthetic) base glyph name.
    Tries, in order: an in-font glyph with that name, Glyphs' name->info
    database, and — if the name itself carries extra dot-suffixes stacked
    before the positional one (e.g. "beh.alt01.fina" -> base "beh.alt01")
    — progressively strips trailing dot-segments and retries.
    """
    candidate = base_name
    seen = set()
    while candidate and candidate not in seen:
        seen.add(candidate)

        base_glyph = font.glyphs[candidate]
        if base_glyph and base_glyph.unicode:
            try:
                return int(base_glyph.unicode, 16)
            except ValueError:
                pass

        try:
            glyph_info = Glyphs.glyphInfoForName(candidate)
            if glyph_info and glyph_info.unicode:
                return int(glyph_info.unicode, 16)
        except Exception:
            pass

        if '.' not in candidate:
            break
        candidate = candidate.rsplit('.', 1)[0]

    return None


def arabic_positional_lookup(font, glyph_name):
    """Return unicode_int for an Arabic positional form (.init/.medi/.fina/.isol), or None."""
    base_name, suffix = strip_positional_suffix(glyph_name)
    if suffix is None:
        return None

    base_unicode = find_base_unicode(font, base_name)
    if base_unicode is None or base_unicode not in ARABIC_FORMS:
        return None

    form_idx = FORM_INDEX_BY_SUFFIX.get(suffix)
    if form_idx is None:
        return None

    return ARABIC_FORMS[base_unicode][form_idx]


# ---------- generic (non-Arabic) resolution ----------

def real_unicode_for(glyph_name):
    """
    Ask Glyphs' built-in glyph info database for the standard unicode of a name.
    Returns a hex string like '002D', or None if unknown / no standard codepoint.
    """
    try:
        info = Glyphs.glyphInfoForName_(glyph_name)
        if info and info.unicode:
            return info.unicode.upper().zfill(4)
    except Exception:
        pass
    return None


def get_pua_in_use(font):
    used = set()
    for g in font.glyphs:
        if g.unicode:
            try:
                cp = int(g.unicode, 16)
                if PUA_START_DEFAULT <= cp <= PUA_END:
                    used.add(cp)
            except ValueError:
                pass
    return used


def pua_slots(start, used):
    cp = start
    while cp <= PUA_END:
        if cp not in used:
            yield cp
        cp += 1


# ---------- collection ----------

def glyphs_in_scope(font):
    if font.selectedLayers:
        seen = set()
        scoped = []
        for layer in font.selectedLayers:
            g = layer.parent
            if id(g) not in seen:
                seen.add(id(g))
                scoped.append(g)
        return scoped
    return list(font.glyphs)


def collect(font):
    """
    Resolve every unicode-less glyph in scope, Arabic rules first:
      arabic_hits : [(glyph, cp, category)]  — direct mapping or positional form
      real_uni    : [(glyph, hex_str)]       — Glyphs' generic name->unicode db
      for_pua     : [glyph]                  — nothing matched, needs PUA
    """
    arabic_hits = []
    real_uni = []
    for_pua = []
    already_skipped = 0

    for g in sorted(glyphs_in_scope(font), key=lambda x: x.name.lower()):
        if not g.export:
            continue
        if g.unicode:
            already_skipped += 1
            continue

        direct = arabic_direct_lookup(g.name)
        if direct:
            cp, category = direct
            arabic_hits.append((g, cp, category))
            continue

        positional = arabic_positional_lookup(font, g.name)
        if positional:
            arabic_hits.append((g, positional, "positional"))
            continue

        uni = real_unicode_for(g.name)
        if uni:
            real_uni.append((g, uni))
            continue

        for_pua.append(g)

    return arabic_hits, real_uni, for_pua, already_skipped


# ---------- dialogs ----------

def ask_start_codepoint():
    alert = NSAlert.alloc().init()
    alert.setMessageText_("Assign Unicode to Glyphs")
    alert.setInformativeText_(
        "Arabic glyphs (marks, positional forms, ligatures) get their\n"
        "correct Unicode/presentation-form value first.\n"
        "Everything else with a known standard unicode gets that.\n"
        "The rest (ligatures, alternates, etc.) get PUA.\n\n"
        "PUA start codepoint (hex):"
    )
    alert.addButtonWithTitle_("Preview…")
    alert.addButtonWithTitle_("Cancel")

    tf = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 24))
    tf.setStringValue_("E000")
    alert.setAccessoryView_(tf)
    alert.layout()
    alert.window().setInitialFirstResponder_(tf)

    if alert.runModal() != NSAlertFirstButtonReturn:
        return None

    raw = tf.stringValue().strip().upper().lstrip("U+").lstrip("0x")
    try:
        cp = int(raw, 16)
        if not (PUA_START_DEFAULT <= cp <= PUA_END):
            Glyphs.showNotification("Assign Unicode", f"U+{cp:04X} is outside PUA range (E000–F8FF).")
            return None
        return cp
    except ValueError:
        Glyphs.showNotification("Assign Unicode", f"'{raw}' is not a valid hex codepoint.")
        return None


def show_preview(arabic_hits, real_uni, pua_assignments, already_skipped):
    rows = []

    if already_skipped:
        rows.append(f"ℹ️  {already_skipped} glyph(s) already have unicode — skipped.")
        rows.append("")

    if arabic_hits:
        rows.append(f"── ARABIC ({len(arabic_hits)}) ──────────────────────────────")
        rows.append(f"  {'GLYPH':<32}  ASSIGN         TYPE")
        rows.append(f"  {'─'*32}  {'─'*11}  {'─'*10}")
        for g, cp, category in arabic_hits:
            rows.append(f"  {g.name:<32}  U+{cp:04X}       {category}")
        rows.append("")

    if real_uni:
        rows.append(f"── REAL UNICODE ({len(real_uni)}) ──────────────────────────────")
        rows.append(f"  {'GLYPH':<32}  ASSIGN")
        rows.append(f"  {'─'*32}  {'─'*10}")
        for g, uni in real_uni:
            try:
                char_preview = f"  ({chr(int(uni, 16))})"
            except Exception:
                char_preview = ""
            rows.append(f"  {g.name:<32}  U+{uni}{char_preview}")
        rows.append("")

    if pua_assignments:
        rows.append(f"── PUA ({len(pua_assignments)}) ────────────────────────────────────")
        rows.append(f"  {'GLYPH':<32}  ASSIGN")
        rows.append(f"  {'─'*32}  {'─'*10}")
        for g, cp in pua_assignments:
            rows.append(f"  {g.name:<32}  U+{cp:04X}")

    if not arabic_hits and not real_uni and not pua_assignments:
        rows.append("Nothing to assign.")

    content = "\n".join(rows)

    scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, 480, 320))
    scroll.setHasVerticalScroller_(True)
    scroll.setHasHorizontalScroller_(True)
    scroll.setAutohidesScrollers_(True)
    scroll.setBorderType_(2)

    tv = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 480, 320))
    tv.setString_(content)
    tv.setEditable_(False)
    tv.setSelectable_(True)
    tv.setFont_(NSFont.fontWithName_size_("Menlo", 11) or NSFont.userFixedPitchFontOfSize_(11))
    tv.setBackgroundColor_(NSColor.textBackgroundColor())
    tv.setTextColor_(NSColor.textColor())
    tv.setHorizontallyResizable_(True)
    tv.setVerticallyResizable_(True)
    tv.textContainer().setWidthTracksTextView_(False)
    tv.textContainer().setContainerSize_(NSMakeSize(9999, 9999))
    scroll.setDocumentView_(tv)

    total = len(arabic_hits) + len(real_uni) + len(pua_assignments)
    alert = NSAlert.alloc().init()
    alert.setMessageText_(f"Preview — {total} glyph(s) to assign")
    alert.setInformativeText_(
        f"{len(arabic_hits)} Arabic  +  {len(real_uni)} real unicode  +  {len(pua_assignments)} PUA\n"
        "Review below, then click Apply."
    )
    alert.addButtonWithTitle_("Apply")
    alert.addButtonWithTitle_("Cancel")
    alert.setAccessoryView_(scroll)
    alert.layout()

    return alert.runModal() == NSAlertFirstButtonReturn


# ---------- main ----------

font = Glyphs.font

if not font:
    print("No font open.")
else:
    start_cp = ask_start_codepoint()

    if start_cp is None:
        print("Cancelled.")
    else:
        arabic_hits, real_uni, for_pua, already_skipped = collect(font)

        pua_in_use   = get_pua_in_use(font)
        slot_gen     = pua_slots(start_cp, pua_in_use)
        pua_assignments = []

        for g in for_pua:
            try:
                pua_assignments.append((g, next(slot_gen)))
            except StopIteration:
                print("⚠️  PUA range exhausted before all glyphs were assigned!")
                break

        if not arabic_hits and not real_uni and not pua_assignments:
            Glyphs.showNotification("Assign Unicode", "No exported glyphs without unicode found.")
        else:
            confirmed = show_preview(arabic_hits, real_uni, pua_assignments, already_skipped)

            if not confirmed:
                print("Cancelled — no changes made.")
            else:
                font.disableUpdateInterface()
                try:
                    for g, cp, _category in arabic_hits:
                        g.unicode = "%04X" % cp
                    for g, uni in real_uni:
                        g.unicode = uni
                    for g, cp in pua_assignments:
                        g.unicode = "{:04X}".format(cp)
                finally:
                    font.enableUpdateInterface()

                print("=" * 60)
                print(f"{font.familyName} — UNICODE ASSIGNMENT")
                print(f"Arabic assigned       : {len(arabic_hits)}")
                print(f"Real unicode assigned : {len(real_uni)}")
                print(f"PUA assigned          : {len(pua_assignments)}")
                print(f"Already had unicode   : {already_skipped} (skipped)")
                print("=" * 60)

                if arabic_hits:
                    print("\n── ARABIC ──")
                    for g, cp, category in arabic_hits:
                        print(f"  {g.name:<32}  U+{cp:04X}  ({category})")

                if real_uni:
                    print("\n── REAL UNICODE ──")
                    for g, uni in real_uni:
                        print(f"  {g.name:<32}  U+{uni}")

                if pua_assignments:
                    print("\n── PUA ──")
                    for g, cp in pua_assignments:
                        print(f"  {g.name:<32}  U+{cp:04X}")

                total = len(arabic_hits) + len(real_uni) + len(pua_assignments)
                print(f"\n✅ Done. {total} glyph(s) assigned.")
                Glyphs.showNotification(
                    "Assign Unicode — Done",
                    f"{len(arabic_hits)} Arabic + {len(real_uni)} real unicode + {len(pua_assignments)} PUA assigned."
                )
