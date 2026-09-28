# MenuTitle: Blend Between Paths
# -*- coding: utf-8 -*-
"""
Creates intermediate paths between two selected paths, similar to Illustrator's Blend Tool.
Select exactly 2 paths and run this script to create blended steps between them.
"""

from vanilla import Window, TextBox, EditText, Button, CheckBox
from GlyphsApp import GSPath, GSNode, GSOFFCURVE, GSCURVE, GSLINE

class BlendPathsController:
    
    def __init__(self):
        self.w = Window((300, 160), "Blend Between Paths")
        
        self.w.text1 = TextBox((15, 15, -15, 20), "Number of steps between paths:")
        
        self.w.steps = EditText((15, 40, -15, 22), "1")
        
        self.w.deleteOriginal = CheckBox((15, 75, -15, 20), "Delete original paths", value=False)
        
        self.w.blendButton = Button((15, 110, -15, 30), "Create Blend", callback=self.createBlend)
        
        self.w.open()
    
    def getSelectedPaths(self):
        """Get exactly 2 selected paths from current layer"""
        font = Glyphs.font
        if not font or not font.selectedLayers:
            return None, None
        
        layer = font.selectedLayers[0]
        selectedPaths = [path for path in layer.paths if path.selected]
        
        return layer, selectedPaths
    
    def pathBoundsDiagonal(self, path):
        """Bounding-box diagonal of a path's nodes, used to judge whether a
        start-point mismatch is significant relative to the shape's own size."""
        xs = [n.position.x for n in path.nodes]
        ys = [n.position.y for n in path.nodes]
        if not xs:
            return 1.0
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        return max(1.0, (width ** 2 + height ** 2) ** 0.5)

    def bestRotationOffset(self, path1, path2):
        """
        Find the rotation offset for path2's node list that best aligns its
        corresponding node positions with path1 (both closed contours with an
        otherwise arbitrary start index). Returns (offset, avg_distance).
        """
        n = len(path1.nodes)
        if n == 0:
            return 0, 0.0
        best_offset = 0
        best_total = None
        for offset in range(n):
            total = 0.0
            for i in range(n):
                n1 = path1.nodes[i]
                n2 = path2.nodes[(i + offset) % n]
                total += ((n1.position.x - n2.position.x) ** 2 +
                          (n1.position.y - n2.position.y) ** 2) ** 0.5
            if best_total is None or total < best_total:
                best_total = total
                best_offset = offset
        return best_offset, (best_total / n if n else 0.0)

    def rotateNodes(self, path, offset):
        """
        Rotate a closed path's node list so index `offset` becomes index 0,
        preserving the actual node objects (positions and on/off-curve types).
        """
        if offset == 0:
            return
        nodes = list(path.nodes)
        rotated = nodes[offset:] + nodes[:offset]
        for existing in nodes:
            path.nodes.remove(existing)
        for node in rotated:
            path.nodes.append(node)

    def checkAndFixDirection(self, path1, path2):
        """
        Check if paths have same direction, reverse path2 if needed. Also
        checks for a rotational start-point mismatch — both paths can have
        matching winding but path2's node 0 may not be the same geometric
        position as path1's node 0, which still produces a garbled blend.
        """
        # Simple check: compare if paths are going in same general direction
        # by checking distance between first few corresponding nodes

        if len(path1.nodes) < 2 or len(path2.nodes) < 2:
            return path2

        # Calculate distance with normal order
        dist_normal = 0
        for i in range(min(3, len(path1.nodes))):
            n1 = path1.nodes[i]
            n2 = path2.nodes[i]
            dist_normal += ((n1.position.x - n2.position.x) ** 2 +
                           (n1.position.y - n2.position.y) ** 2) ** 0.5

        # Calculate distance with reversed order
        dist_reversed = 0
        for i in range(min(3, len(path1.nodes))):
            n1 = path1.nodes[i]
            n2 = path2.nodes[-(i+1)]
            dist_reversed += ((n1.position.x - n2.position.x) ** 2 +
                             (n1.position.y - n2.position.y) ** 2) ** 0.5

        # If reversed order gives smaller distance, reverse path2
        if dist_reversed < dist_normal:
            path2.reverse()

        # Rotational-offset check (only meaningful once node counts match,
        # which is verified by the caller before this runs).
        if len(path1.nodes) == len(path2.nodes):
            diag = self.pathBoundsDiagonal(path1)

            current_dist = 0.0
            for i in range(len(path1.nodes)):
                n1 = path1.nodes[i]
                n2 = path2.nodes[i]
                current_dist += ((n1.position.x - n2.position.x) ** 2 +
                                  (n1.position.y - n2.position.y) ** 2) ** 0.5
            current_avg = current_dist / len(path1.nodes)

            # Skip the O(n^2) search unless the current alignment already
            # looks bad relative to the shape's own size.
            if current_avg > diag * 0.15:
                offset, best_avg = self.bestRotationOffset(path1, path2)
                if offset != 0 and best_avg < current_avg * 0.5:
                    self.rotateNodes(path2, offset)
                    print(f"Blend: re-aligned path2's start index by {offset} node(s) "
                          "to fix an apparent rotational mismatch.")
                elif best_avg >= current_avg * 0.5:
                    print("Blend: paths may start at different positions around the shape "
                          "(possible rotational mismatch) — could not confidently auto-fix; "
                          "check the result carefully.")

        return path2
    
    def interpolatePath(self, path1, path2, factor):
        """Interpolate between two paths at given factor (0.0 to 1.0)"""
        if len(path1.nodes) != len(path2.nodes):
            return None

        for i, (node1, node2) in enumerate(zip(path1.nodes, path2.nodes)):
            if node1.type != node2.type:
                print(f"Blend: node type mismatch at index {i} "
                      f"({node1.type} vs {node2.type}) — aborting this blend.")
                return None

        newPath = GSPath()
        newPath.closed = path1.closed
        
        for i, (node1, node2) in enumerate(zip(path1.nodes, path2.nodes)):
            # Interpolate position
            x = node1.position.x + (node2.position.x - node1.position.x) * factor
            y = node1.position.y + (node2.position.y - node1.position.y) * factor
            
            # Create new node
            newNode = GSNode()
            newNode.position = (x, y)
            newNode.type = node1.type
            
            newPath.nodes.append(newNode)
        
        return newPath
    
    def createBlend(self, sender):
        layer, selectedPaths = self.getSelectedPaths()
        
        if not layer:
            Message("No font or layer selected", "Error")
            return
        
        if len(selectedPaths) != 2:
            Message(f"Please select exactly 2 paths (currently {len(selectedPaths)} selected)", "Error")
            return
        
        try:
            steps = int(self.w.steps.get())
            if steps < 1:
                raise ValueError
        except:
            Message("Please enter a valid number of steps (minimum 1)", "Error")
            return
        
        path1 = selectedPaths[0]
        path2 = selectedPaths[1]
        
        # Check if paths have same number of nodes
        if len(path1.nodes) != len(path2.nodes):
            Message(f"Paths must have the same number of nodes\nPath 1: {len(path1.nodes)} nodes\nPath 2: {len(path2.nodes)} nodes", "Node Count Mismatch")
            return

        # Fix direction (and, where confidently possible, start-point
        # rotational offset) before checking node types line up.
        path2 = self.checkAndFixDirection(path1, path2)

        for i, (n1, n2) in enumerate(zip(path1.nodes, path2.nodes)):
            if n1.type != n2.type:
                Message(
                    f"Paths have matching node counts but different node types at index {i} "
                    f"({n1.type} vs {n2.type}).\nBlending would produce a garbled outline — "
                    "align the path structures first.",
                    "Node Type Mismatch"
                )
                return
        
        # Create intermediate paths
        font = Glyphs.font
        font.disableUpdateInterface()
        
        try:
            for i in range(1, steps + 1):
                factor = i / (steps + 1.0)
                newPath = self.interpolatePath(path1, path2, factor)
                
                if newPath:
                    layer.paths.append(newPath)
            
            # Delete original paths if checkbox is checked
            if self.w.deleteOriginal.get():
                layer.shapes.remove(path1)
                layer.shapes.remove(path2)
            
            Glyphs.showNotification("Blend Created", f"Created {steps} intermediate path(s)")
            self.w.close()
        
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            Message(str(e), "Script Error")
        
        finally:
            font.enableUpdateInterface()
        


# Run the script
BlendPathsController()
