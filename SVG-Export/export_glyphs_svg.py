#MenuTitle: Export Glyphs as SVG…
# -*- coding: utf-8 -*-
"""
Export Glyphs as SVG — FIXED VERSION
Changes from original:
  [FIX 1] _draw_path: closing curve segment no longer dropped for closed paths
  [FIX 2] Component transform: use tuple indexing instead of .m11/.m12 attributes
  [FIX 3] masterForId_: replaced with safe iteration over font.masters
  [NOTE]  Nested components (depth > 1) still skipped — rare in practice
"""
import os
import re
import traceback
from GlyphsApp import Glyphs
from AppKit import (
    NSAlert, NSOpenPanel,
    NSAlertFirstButtonReturn, NSAlertSecondButtonReturn, NSAlertThirdButtonReturn,
)


# ---------- helpers ----------

def safe_filename(name):
    name = name.replace("/", "_slash_")
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def _apply_xform(xform, x, y):
    """xform: (m11, m12, m21, m22, tx, ty)"""
    m11, m12, m21, m22, tx, ty = xform
    return (m11 * x + m21 * y + tx, m12 * x + m22 * y + ty)


def _draw_path(path, pen, xform=(1, 0, 0, 1, 0, 0)):
    nodes = list(path.nodes)
    if not nodes:
        return

    # Rotate list to start at the first on-curve node
    start_idx = 0
    for i, n in enumerate(nodes):
        if n.type in ("line", "curve", "qcurve", "LINE", "CURVE", "QCURVE"):
            start_idx = i
            break
    ordered = nodes[start_idx:] + nodes[:start_idx]

    def pt(node):
        return _apply_xform(xform, node.position.x, node.position.y)

    pen["moveTo"](pt(ordered[0]))

    # [FIX 1] For closed paths, append ordered[0] as a sentinel so the final
    # curveTo (closing segment) is emitted instead of being silently dropped.
    # Without this, the last curve segment becomes a straight closePath line.
    work = ordered[:]
    if path.closed:
        work.append(ordered[0])

    i = 1
    while i < len(work):
        n = work[i]
        t = n.type.lower() if isinstance(n.type, str) else n.type

        if t == "line":
            pen["lineTo"](pt(n))
            i += 1
        elif t == "curve" and i >= 2:
            pen["curveTo"](pt(work[i - 2]), pt(work[i - 1]), pt(n))
            i += 1
        elif t == "qcurve" and i >= 1:
            pen["qCurveTo"](pt(work[i - 1]), pt(n))
            i += 1
        else:
            i += 1

    if path.closed:
        pen["closePath"]()
    else:
        pen["endPath"]()


def _get_comp_transform(comp):
    """
    [FIX 2] In Glyphs 3, comp.transform returns a plain tuple (m11,m12,m21,m22,dx,dy),
    NOT an object with .m11 attributes. Use index access.
    """
    try:
        t = comp.transform
        if isinstance(t, (tuple, list)) and len(t) == 6:
            return (t[0], t[1], t[2], t[3], t[4], t[5])
        # Older Glyphs / NSAffineTransformStruct with named fields
        return (t.m11, t.m12, t.m21, t.m22, t.tX, t.tY)
    except Exception:
        pass
    # Last resort: translation only from position
    try:
        pos = comp.position
        return (1, 0, 0, 1, pos.x, pos.y)
    except Exception:
        return (1, 0, 0, 1, 0, 0)


def _get_base_layer(comp, layer):
    """Resolve a component to its base GSLayer matching the current master."""
    try:
        bl = comp.componentLayer
        if bl is not None:
            return bl
    except Exception:
        pass

    base_glyph = getattr(comp, "component", None)
    if base_glyph is None:
        name = getattr(comp, "componentName", None)
        if name:
            base_glyph = Glyphs.font.glyphs[name]
    if base_glyph is None:
        return None

    for l in base_glyph.layers:
        if l.layerId == layer.layerId or l.associatedMasterId == layer.associatedMasterId:
            return l

    if base_glyph.layers:
        composite_name = getattr(getattr(layer, "parent", None), "name", "?")
        print(
            "⚠️  {}: component '{}' has no layer matching master '{}' — "
            "falling back to its first layer, outline may be from the wrong master.".format(
                composite_name, base_glyph.name, getattr(layer, "associatedMasterId", "?")
            )
        )
        return base_glyph.layers[0]
    return None


def layer_to_svg_path_d(layer):
    """Return SVG path 'd' string for a GSLayer, flattening components."""
    commands = []

    def fmt(pt):
        return "{:g} {:g}".format(pt[0], pt[1])

    def moveTo(pt):   commands.append("M" + fmt(pt))
    def lineTo(pt):   commands.append("L" + fmt(pt))
    def curveTo(a, b, c): commands.append("C" + fmt(a) + " " + fmt(b) + " " + fmt(c))
    def qCurveTo(a, b):   commands.append("Q" + fmt(a) + " " + fmt(b))
    def closePath():  commands.append("Z")
    def endPath():    pass

    pen = {
        "moveTo": moveTo, "lineTo": lineTo,
        "curveTo": curveTo, "qCurveTo": qCurveTo,
        "closePath": closePath, "endPath": endPath,
    }

    for path in layer.paths:
        _draw_path(path, pen)

    for comp in (layer.components or []):
        base_layer = _get_base_layer(comp, layer)
        if base_layer is None:
            continue

        xform = _get_comp_transform(comp)  # [FIX 2]

        for path in base_layer.paths:
            _draw_path(path, pen, xform)

        # Nested components (depth > 1): rare, skipped intentionally
        for sub in (base_layer.components or []):
            sub_base = _get_base_layer(sub, base_layer)
            if sub_base is None:
                continue
            sub_xform = _get_comp_transform(sub)
            # Compose transforms: sub_xform then xform
            sm11, sm12, sm21, sm22, stx, sty = sub_xform
            m11, m12, m21, m22, tx, ty = xform
            composed = (
                m11*sm11 + m21*sm12,
                m12*sm11 + m22*sm12,
                m11*sm21 + m21*sm22,
                m12*sm21 + m22*sm22,
                m11*stx  + m21*sty + tx,
                m12*stx  + m22*sty + ty,
            )
            for path in sub_base.paths:
                _draw_path(path, pen, composed)

    return " ".join(commands)


def layer_to_svg(layer, master):
    width    = int(layer.width) if layer.width else int(master.font.upm)
    ascender  = int(master.ascender)
    descender = int(master.descender)
    view_h = ascender - descender
    view_w = max(width, 1)

    d = layer_to_svg_path_d(layer)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'viewBox="0 {minY} {w} {h}" width="{w}" height="{h}">\n'
        '  <g transform="scale(1,-1)">\n'
        '    <path d="{d}" fill="black"/>\n'
        '  </g>\n'
        '</svg>\n'
    ).format(minY=-ascender, w=view_w, h=view_h, d=d)
    return svg


# ---------- dialog ----------

def ask_scope():
    alert = NSAlert.alloc().init()
    alert.setMessageText_("Export Glyphs as SVG")
    alert.setInformativeText_("Choose which glyphs to export.")
    alert.addButtonWithTitle_("Selected")
    alert.addButtonWithTitle_("All")
    alert.addButtonWithTitle_("Exported only")
    alert.addButtonWithTitle_("Cancel")
    response = alert.runModal()
    if response == NSAlertFirstButtonReturn:    return "selected"
    if response == NSAlertSecondButtonReturn:   return "all"
    if response == NSAlertThirdButtonReturn:    return "exported"
    return None


def ask_output_folder(default_name):
    panel = NSOpenPanel.openPanel()
    panel.setCanChooseFiles_(False)
    panel.setCanChooseDirectories_(True)
    panel.setAllowsMultipleSelection_(False)
    panel.setCanCreateDirectories_(True)
    panel.setPrompt_("Export Here")
    panel.setTitle_("Choose output folder for SVGs")
    if panel.runModal():
        folder = panel.URLs()[0].path()
        sub = os.path.join(folder, default_name)
        if not os.path.exists(sub):
            os.makedirs(sub)
        return sub
    return None


def _master_for_id(font, master_id):
    """[FIX 3] Safe master lookup — avoids Obj-C style masterForId_() call."""
    for m in font.masters:
        if m.id == master_id:
            return m
    return font.masters[0]


# ---------- main ----------

def main():
    font = Glyphs.font
    if font is None:
        Glyphs.showNotification("Export SVG", "No font open.")
        return

    scope = ask_scope()
    if scope is None:
        return

    if scope == "selected":
        layers = list(font.selectedLayers) if font.selectedLayers else []
        if not layers:
            Glyphs.showNotification("Export SVG", "No glyphs selected.")
            return
        master = _master_for_id(font, layers[0].associatedMasterId)  # [FIX 3]
        glyph_layer_pairs = [(l.parent, l) for l in layers]
    else:
        master = font.selectedFontMaster or font.masters[0]
        glyph_layer_pairs = []
        for g in font.glyphs:
            if scope == "exported" and not g.export:
                continue
            layer = g.layers[master.id]
            if layer is None:
                continue
            glyph_layer_pairs.append((g, layer))

    if not glyph_layer_pairs:
        Glyphs.showNotification("Export SVG", "Nothing to export.")
        return

    out_dir_name = "{}-{}-SVG".format(font.familyName, master.name).replace(" ", "_")
    out_dir = ask_output_folder(out_dir_name)
    if out_dir is None:
        return

    count = 0
    errors = 0
    used_filenames = set()
    for g, layer in glyph_layer_pairs:
        try:
            svg = layer_to_svg(layer, master)
            fname = safe_filename(g.name) + ".svg"
            if fname in used_filenames:
                base, ext = os.path.splitext(fname)
                n = 2
                candidate = "{}_{}{}".format(base, n, ext)
                while candidate in used_filenames:
                    n += 1
                    candidate = "{}_{}{}".format(base, n, ext)
                print(
                    "⚠️  Filename collision: '{}' already used by another glyph — "
                    "exporting '{}' as '{}' instead.".format(fname, g.name, candidate)
                )
                fname = candidate
            used_filenames.add(fname)
            with open(os.path.join(out_dir, fname), "w") as f:
                f.write(svg)
            count += 1
        except Exception:
            errors += 1
            print("Error exporting", g.name)
            print(traceback.format_exc())

    msg = "Exported {} glyphs to:\n{}".format(count, out_dir)
    if errors:
        msg += "\n({} errors — see Macro window.)".format(errors)
    Glyphs.showNotification("Export SVG done", msg)
    print(msg)


main()
