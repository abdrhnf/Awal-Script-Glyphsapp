# MenuTitle: SVG Single Line
# -*- coding: utf-8 -*-

# by Awal Studio

__doc__='''
Part of the Awal Studio workflow.

Description:
This script adds stroke attributes to layers, creates a new layer with a timestamp, 
sets up a Weight axis, and adds "Regular" and "OTF-SVG" instances.

How to use:
1. Open your font in GlyphsApp.
2. Select the glyphs you want to process (or select none to process all).
3. Run the script from the Script menu.
4. Check the added instances in Font Info > Exports.

Author: Abdurrahman Hanif — Awal Studio
Version: 1.0
Date: December 2025
'''

import datetime
from Foundation import NSColor

# Color index 6 in Glyphs' fixed layer-color palette is Light Blue, not
# black (palette order: 0 red, 1 orange, 2 brown, 3 yellow, 4 light green,
# 5 dark green, 6 light blue, 7 dark blue, 8 purple, 9 magenta, 10 light
# gray, 11 dark gray/charcoal). Kept as-is since it's only a visual marker
# for the timestamped comparison layer, but the old comment was wrong.
colorID = 6

# Define stroke width and height
strokeWidth = 30
strokeHeight = 30
lineCapStart = 1
lineCapEnd = 1

# Function to add stroke attributes to paths
def add_stroke_attributes(layer):
    for path in layer.paths:
        path.attributes['strokeColor'] = NSColor.blackColor()
        path.attributes['strokeWidth'] = strokeWidth
        path.attributes['strokeHeight'] = strokeHeight
        path.attributes['lineCapStart'] = lineCapStart
        path.attributes['lineCapEnd'] = lineCapEnd

# Main script
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
        layers_to_process = font.selectedLayers
    else:
        layers_to_process = []
        for g in font.glyphs:
            layer = g.layers[font.selectedFontMaster.id]
            if layer is None:
                print(f"⚠️  Skipping {g.name}: no layer for the current master (sparse layer).")
                continue
            layers_to_process.append(layer)

    # STEP 1: Process each layer (add stroke, create duplicate with timestamp)
    for layer in layers_to_process:
        glyph = layer.parent
        
        # Apply stroke attributes to the original layer
        add_stroke_attributes(layer)
        
        # Create a duplicate of the layer for backup/comparison
        newLayer = layer.copy()
        
        # Ensure the layer name is a string
        if newLayer.name is None:
            newLayer.name = ""
        
        # Create a timestamp for naming (e.g., "Nov 30 25, 22:41")
        timestamp = datetime.datetime.now().strftime("%b %-d %y, %H:%M")
        
        # Update the layer name with the current timestamp
        if newLayer.isBraceLayer:
            newLayer.name += " " + timestamp
            newLayer.setAttribute_forKey_(False, "isBraceLayer")
        else:
            newLayer.name = timestamp
        
        # Set the color of the new layer (color ID 6 = black)
        newLayer.setAttribute_forKey_(colorID, "color")
        
        # Apply stroke attributes to all paths in the new layer
        add_stroke_attributes(newLayer)
        
        # Add the new timestamped layer to the glyph
        glyph.layers.append(newLayer)

    # STEP 2: Set up the Weight axis for variable font
    # This creates a "wght" axis that can be used for variable fonts.
    # Re-runs of this script must not duplicate the axis, so reuse an
    # existing "wght" axis if one is already there.
    weightAxis = None
    for axis in font.axes:
        if axis.axisTag == "wght":
            weightAxis = axis
            break
    if weightAxis is None:
        weightAxis = GSAxis()
        weightAxis.name = "Weight"
        weightAxis.axisTag = "wght"
        weightAxis.hidden = False
        font.axes.append(weightAxis)

    # STEP 3: Set the current master's Weight axis coordinate to 50
    # This positions the master at the middle of the weight range
    for master in font.masters:
        master.axes[weightAxis.axisTag] = 50

    # STEP 4: Add two instances with different axis values
    # These will be used for exporting different font weights.
    # Re-runs must not duplicate instances — update in place if one with
    # this name already exists.
    def add_instance(style_name, weight_value):
        for existing in font.instances:
            if existing.name == style_name:
                existing.axes[weightAxis.axisTag] = weight_value
                return
        instance = GSInstance()
        instance.name = style_name
        instance.customParameters["postscriptFontName"] = f"{font.familyName} {style_name}"
        instance.axes[weightAxis.axisTag] = weight_value
        font.instances.append(instance)

    # Add Regular instance at weight 10 (lighter)
    add_instance("Regular", 10)
    # Add OTF-SVG instance at weight 20 (slightly heavier, for SVG export)
    add_instance("OTF-SVG", 20)

    print("✅ Script completed successfully!")
    print("- Weight axis added (wght)")
    print("- Current master set to weight 50")
    print("- Two instances added: Regular (10) and OTF-SVG (20)")
    print("- Stroke attributes applied to selected/all layers")
