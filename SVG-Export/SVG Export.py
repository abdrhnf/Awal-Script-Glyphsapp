# MenuTitle: SVG Export
# -*- coding: utf-8 -*-
from __future__ import division, print_function, unicode_literals
import os
import Cocoa
from GlyphsApp import Glyphs, Message
from Foundation import NSClassFromString

"""
Export selected glyphs as SVG files.
Features:
- Auto-Normalization: Fits glyph into a 512x512 box (conceptually, though currently uses bounds).
- Centering: Ensures the glyph is centered in the viewport.
- Batch export: Saves all selected glyphs to a chosen folder.
"""

# Constants


def get_destination_folder():
	"""
	Opens a dialog for the user to select the export destination folder.
	Returns:
		str: The path to the selected folder, or None if cancelled.
	"""
	panel = Cocoa.NSOpenPanel.openPanel()
	panel.setCanChooseDirectories_(True)
	panel.setCanChooseFiles_(False)
	panel.setAllowsMultipleSelection_(False)
	panel.setCanCreateDirectories_(True)
	
	if panel.runModal() == Cocoa.NSFileHandlingPanelOKButton:
		return panel.URLs()[0].path()
	return None

def process_layer_geometry(layer):
	"""
	Creates a copy of the layer and applies preprocessing:
	1. Decompose Components
	2. Expand Stroke (if possible)
	3. Correct Path Direction
	4. Remove Overlap
	
	Returns:
		GSLayer: A processed copy of the layer, or None if failed.
	"""
	# Create a fresh copy
	temp_layer = layer.copy()
	
	glyph_name = layer.parent.name
	
	try:
		# 1. Decompose
		temp_layer.decomposeComponents()
		
		# 2. Expand Stroke
		ExpandFilter = NSClassFromString("GlyphsFilterExpandOutline")
		if ExpandFilter:
			try:
				# Glyphs 3 API signature might vary, standard ObjC bridge way
				ExpandFilter.alloc().init().runFilter_layer_error_(temp_layer, temp_layer, None)
			except Exception as e:
				print(f"Warning: Expand Stroke filter failed for {glyph_name}: {e}")
		
		# 3. Correct Path Direction (Fix winding before removing overlap)
		temp_layer.correctPathDirection()
		
		# 4. Remove Overlap
		temp_layer.removeOverlap()
		
		return temp_layer
		
	except Exception as e:
		print(f"Preprocessing failed for {glyph_name}: {e}")
		return None

def get_svg_path_data(bezier_path):
	"""
	Converts a NSBezierPath to an SVG path data string.
	"""
	svg_parts = []
	try:
		count = bezier_path.elementCount()
		for i in range(count):
			element, pts = bezier_path.elementAtIndex_associatedPoints_(i)
			if element == Cocoa.NSMoveToBezierPathElement:
				svg_parts.append(f"M{pts[0].x:.3f},{pts[0].y:.3f}")
			elif element == Cocoa.NSLineToBezierPathElement:
				svg_parts.append(f"L{pts[0].x:.3f},{pts[0].y:.3f}")
			elif element == Cocoa.NSCurveToBezierPathElement:
				svg_parts.append(f"C{pts[0].x:.3f},{pts[0].y:.3f} {pts[1].x:.3f},{pts[1].y:.3f} {pts[2].x:.3f},{pts[2].y:.3f}")
			elif element == Cocoa.NSClosePathBezierPathElement:
				svg_parts.append("Z")
		return " ".join(svg_parts)
	except Exception as e:
		print(f"Error generating path data: {e}")
		return ""

def process_and_get_transformed_path_data(layer):
	"""
	Processes the layer features and returns the SVG path data string
	along with width and height, transformed to be flip-Y corrected.
	
	Returns:
		tuple: (path_data, width, height) or (None, 0, 0)
	"""
	glyph_name = layer.parent.name
	
	# 1. Preprocess Geometry
	processed_layer = process_layer_geometry(layer)
	
	# Fallback if processing failed or result is empty
	bp = processed_layer.bezierPath if processed_layer else None
	if bp is None or bp.elementCount() == 0:
		print(f"Warning: Processed path is empty for {glyph_name}. Trying fallback (decomposed orig).")
		processed_layer = layer.copyDecomposedLayer()
		bp = processed_layer.bezierPath
	
	if bp is None or bp.elementCount() == 0:
		print(f"Skipping {glyph_name}: No paths found after processing and fallback.")
		return None, 0, 0

	# 2. Calculate Bounds
	bounds = bp.bounds()
	x, y = bounds.origin.x, bounds.origin.y
	w, h = bounds.size.width, bounds.size.height

	if w <= 0 or h <= 0:
		print(f"Skipping {glyph_name}: No visual paths found.")
		return None, 0, 0

	# 3. Apply Transformations
	# SVG Coordinate System: Origin is top-left, Y increases downwards.
	# Glyphs Coordinate System: Origin is bottom-left, Y increases upwards.
	# We need to:
	#   (a) Translate origin to (0,0)
	#   (b) Flip Y axis
	#   (c) Translate down by height (since flip moves it to negative Y)
	
	transform = Cocoa.NSAffineTransform.transform()
	transform.translateXBy_yBy_(0, h)         # 3. Move 'down'
	transform.scaleXBy_yBy_(1.0, -1.0)       # 2. Flip
	transform.translateXBy_yBy_(-x, -y)      # 1. Zero origin
	
	bp.transformUsingAffineTransform_(transform)
	
	# 4. Generate SVG Data
	path_data = get_svg_path_data(bp)
	return path_data, w, h

def save_svg_file(glyph_name, path_data, w, h, folder_path):
	"""
	Saves the SVG content to a file.
	"""
	svg_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg width="{w:.2f}" height="{h:.2f}" viewBox="0 0 {w:.2f} {h:.2f}" xmlns="http://www.w3.org/2000/svg">
	<path d="{path_data}" fill="currentColor" fill-rule="nonzero"/>
</svg>"""

	filename = f"{glyph_name}.svg"
	file_path = os.path.join(folder_path, filename)
	
	try:
		with open(file_path, "w", encoding="utf-8") as f:
			f.write(svg_content)
		return True
	except IOError as e:
		print(f"Failed to save {filename}: {e}")
		return False

def main():
	font = Glyphs.font
	if not font:
		Message("No font open", "Please open a .glyphs file first.")
		return

	selected_layers = font.selectedLayers
	if not selected_layers:
		Message("No selection", "Please select glyphs to export in the Font View.")
		return

	export_root = get_destination_folder()
	if not export_root:
		return

	export_path = export_root

	processed_count = 0
	for layer in selected_layers:
		path_data, w, h = process_and_get_transformed_path_data(layer)
		if path_data:
			if save_svg_file(layer.parent.name, path_data, w, h, export_path):
				processed_count += 1
	
	Glyphs.showNotification("SVG Export Complete", f"Exported {processed_count} glyphs to {export_path}")

if __name__ == "__main__":
	main()
