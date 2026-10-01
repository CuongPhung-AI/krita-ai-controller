"""
Drawing controller for Krita AI Bridge.
Executes canvas, document, brush, color, and layer operations
on Krita's main thread.
"""

import base64
import io
import os
import sys
import traceback
from PyQt6.QtCore import QPoint, QRectF, QBuffer, QIODevice
from PyQt6.QtGui import QColor, QImage, QPainterPath
from krita import Krita, ManagedColor
try:
    from krita import InfoObject
except ImportError:
    InfoObject = None


def parse_color(c_val):
    """Parse color from string, tuple, list, or dict into QColor."""
    if isinstance(c_val, QColor):
        return c_val
    if isinstance(c_val, str):
        c = QColor(c_val)
        if not c.isValid():
            c = QColor.fromString(c_val)
        return c
    elif isinstance(c_val, (list, tuple)):
        if len(c_val) == 3:
            return QColor(int(c_val[0]), int(c_val[1]), int(c_val[2]), 255)
        elif len(c_val) >= 4:
            return QColor(int(c_val[0]), int(c_val[1]), int(c_val[2]), int(c_val[3]))
    elif isinstance(c_val, dict):
        return QColor(
            int(c_val.get("r", 0)),
            int(c_val.get("g", 0)),
            int(c_val.get("b", 0)),
            int(c_val.get("a", 255))
        )
    return QColor(c_val)


class DrawingController:
    """Controls Krita documents, layers, tools, and drawing operations."""

    def __init__(self):
        self.app = Krita.instance()

    def _get_active_doc(self, required=True):
        doc = self.app.activeDocument()
        if not doc and required:
            docs = self.app.documents()
            if docs:
                doc = docs[0]
                self.app.setActiveDocument(doc)
            else:
                raise RuntimeError("No active document in Krita")
        return doc

    def _get_active_view(self):
        window = self.app.activeWindow()
        if window:
            view = window.activeView()
            if view:
                return view
            doc = self._get_active_doc(required=False)
            if doc:
                return window.addView(doc)
        views = self.app.views()
        if views:
            return views[0]
        return None

    def _get_or_create_paint_layer(self, doc):
        node = doc.activeNode()
        if node and node.type() == "paintlayer":
            return node
        # Look for any paint layer
        for child in doc.rootNode().childNodes():
            if child.type() == "paintlayer":
                doc.setActiveNode(child)
                return child
        # Create a new paint layer
        new_layer = doc.createNode("Paint Layer", "paintlayer")
        doc.rootNode().addChildNode(new_layer, None)
        doc.setActiveNode(new_layer)
        return new_layer

    def get_status(self):
        """Return comprehensive status of Krita session."""
        doc = self._get_active_doc(required=False)
        window = self.app.activeWindow()
        view = self._get_active_view()

        status = {
            "version": self.app.version(),
            "batchmode": self.app.batchmode(),
            "documents_count": len(self.app.documents()),
            "has_active_document": doc is not None,
            "active_document": None,
            "active_layer": None,
            "layers": [],
            "active_brush": None,
            "colors": {
                "foreground": None,
                "background": None
            }
        }

        if doc:
            status["active_document"] = {
                "name": doc.name(),
                "width": doc.width(),
                "height": doc.height(),
                "color_model": doc.colorModel(),
                "color_depth": doc.colorDepth(),
                "color_profile": doc.colorProfile(),
                "resolution": doc.resolution(),
                "file_name": doc.fileName(),
                "modified": doc.modified(),
            }

            active_node = doc.activeNode()
            if active_node:
                status["active_layer"] = {
                    "name": active_node.name(),
                    "type": active_node.type(),
                    "visible": active_node.visible(),
                    "opacity": active_node.opacity(),
                    "locked": active_node.locked(),
                }

            def walk_nodes(parent):
                nodes = []
                for child in parent.childNodes():
                    nodes.append({
                        "name": child.name(),
                        "type": child.type(),
                        "visible": child.visible(),
                        "opacity": child.opacity(),
                        "children": walk_nodes(child) if child.childNodes() else []
                    })
                return nodes

            status["layers"] = walk_nodes(doc.rootNode())

        if view:
            preset = view.currentBrushPreset()
            fg = view.foregroundColor()
            bg = view.backgroundColor()
            status["active_brush"] = {
                "preset": preset.name() if preset else None,
                "size": view.brushSize(),
                "opacity": view.paintingOpacity(),
                "flow": view.paintingFlow()
            }
            if fg:
                c = fg.colorForCanvas(view.canvas())
                status["colors"]["foreground"] = c.name()
            if bg:
                c = bg.colorForCanvas(view.canvas())
                status["colors"]["background"] = c.name()

        return status

    def get_brushes(self):
        """Return all available brush preset names."""
        presets = self.app.resources("preset")
        return {
            "count": len(presets),
            "presets": sorted(list(presets.keys()))
        }

    def get_snapshot(self, bounds=None):
        """Return rendered canvas projection as PNG bytes."""
        doc = self._get_active_doc(required=True)
        doc.refreshProjection()
        doc.waitForDone()

        if bounds and isinstance(bounds, (list, tuple)) and len(bounds) == 4:
            x, y, w, h = int(bounds[0]), int(bounds[1]), int(bounds[2]), int(bounds[3])
        else:
            x, y, w, h = 0, 0, doc.width(), doc.height()

        qimage = doc.projection(x, y, w, h)
        if qimage.isNull():
            raise RuntimeError("Failed to capture canvas projection (null image returned)")

        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        qimage.save(buf, "PNG")
        png_bytes = bytes(buf.data())
        buf.close()
        return png_bytes

    def create_document(self, data):
        """Create a new document and register it in active window."""
        w = int(data.get("width", 1920))
        h = int(data.get("height", 1080))
        name = str(data.get("name", "New Canvas"))
        color_model = str(data.get("color_model", "RGBA"))
        color_depth = str(data.get("color_depth", "U8"))
        profile = str(data.get("profile", ""))
        resolution = float(data.get("resolution", 120.0))

        doc = self.app.createDocument(w, h, name, color_model, color_depth, profile, resolution)
        if not doc:
            raise RuntimeError(f"Failed to create document '{name}' ({w}x{h})")

        window = self.app.activeWindow()
        if window:
            window.addView(doc)
            self.app.setActiveDocument(doc)

        return {
            "created": True,
            "name": doc.name(),
            "width": doc.width(),
            "height": doc.height(),
            "color_model": doc.colorModel(),
            "color_depth": doc.colorDepth()
        }

    def save_document(self, data):
        """Save active document to file silently without modal popups."""
        doc = self._get_active_doc(required=True)
        path = data.get("path")
        if not path:
            doc_file = doc.fileName() if hasattr(doc, "fileName") else ""
            if doc_file:
                path = doc_file
            else:
                raise ValueError("Parameter 'path' is required to save an untitled document")

        path = os.path.abspath(os.path.expanduser(os.path.expandvars(str(path).strip())))
        parent_dir = os.path.dirname(path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        prev_app_batch = self.app.batchmode() if hasattr(self.app, "batchmode") else False
        prev_doc_batch = doc.batchmode() if hasattr(doc, "batchmode") else False

        try:
            if hasattr(self.app, "setBatchmode"):
                self.app.setBatchmode(True)
            if hasattr(doc, "setBatchmode"):
                doc.setBatchmode(True)

            if hasattr(doc, "refreshProjection"):
                try:
                    doc.refreshProjection()
                except Exception:
                    pass

            if hasattr(doc, "waitForDone"):
                try:
                    doc.waitForDone()
                except Exception:
                    pass

            ext = os.path.splitext(path)[1].lower()
            raster_exts = {
                ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif",
                ".bmp", ".gif", ".exr", ".tga", ".ppm", ".pgm",
                ".pbm", ".hdr", ".jxl", ".ico"
            }

            saved = False
            if ext in raster_exts and hasattr(doc, "exportImage"):
                try:
                    info = None
                    try:
                        from krita import InfoObject
                        info = InfoObject()
                    except (ImportError, Exception):
                        pass

                    if info is not None:
                        options = data.get("export_options") or data.get("options")
                        if isinstance(options, dict) and hasattr(info, "setProperty"):
                            for k, v in options.items():
                                try:
                                    info.setProperty(str(k), v)
                                except Exception:
                                    pass
                        saved = doc.exportImage(path, info)
                    else:
                        saved = doc.saveAs(path)
                except Exception:
                    saved = False

            if not saved:
                saved = doc.saveAs(path)

            if hasattr(doc, "waitForDone"):
                try:
                    doc.waitForDone()
                except Exception:
                    pass

            if not saved or not os.path.exists(path):
                raise RuntimeError(f"Failed to save document to '{path}'")

            return {"saved": True, "path": path}
        finally:
            if hasattr(doc, "setBatchmode") and prev_doc_batch is not None:
                try:
                    doc.setBatchmode(prev_doc_batch)
                except Exception:
                    pass
            if hasattr(self.app, "setBatchmode") and prev_app_batch is not None:
                try:
                    self.app.setBatchmode(prev_app_batch)
                except Exception:
                    pass

    def create_layer(self, data):
        """Create a paint, vector, or group layer."""
        doc = self._get_active_doc(required=True)
        name = str(data.get("name", "Layer"))
        ltype = str(data.get("type", "paint")).lower()

        if "vector" in ltype:
            node = doc.createVectorLayer(name)
        elif "group" in ltype:
            node = doc.createGroupLayer(name)
        else:
            node = doc.createNode(name, "paintlayer")

        parent_name = data.get("parent")
        parent = doc.nodeByName(parent_name) if parent_name else doc.rootNode()
        if not parent:
            parent = doc.rootNode()

        above_name = data.get("above")
        above = doc.nodeByName(above_name) if above_name else None

        ok = parent.addChildNode(node, above)
        if not ok:
            raise RuntimeError(f"Failed to add layer '{name}' to node tree")

        doc.setActiveNode(node)
        doc.refreshProjection()
        return {
            "created": True,
            "name": node.name(),
            "type": node.type()
        }

    def select_layer(self, data):
        """Select an existing layer by name."""
        doc = self._get_active_doc(required=True)
        name = data.get("name")
        if not name:
            raise ValueError("Parameter 'name' is required")
        node = doc.nodeByName(name)
        if not node:
            raise ValueError(f"Layer '{name}' not found in active document")
        doc.setActiveNode(node)
        return {
            "selected": True,
            "name": node.name(),
            "type": node.type()
        }

    def set_color(self, data):
        """Set active foreground and/or background colors."""
        view = self._get_active_view()
        if not view:
            raise RuntimeError("No active view in Krita to set color")

        fg = data.get("foreground")
        bg = data.get("background")

        if fg is not None:
            qc = parse_color(fg)
            mc = ManagedColor.fromQColor(qc)
            view.setForeGroundColor(mc)

        if bg is not None:
            qc = parse_color(bg)
            mc = ManagedColor.fromQColor(qc)
            view.setBackGroundColor(mc)

        return {"updated": True}

    def set_brush(self, data):
        """Set active brush preset, size, opacity, and flow."""
        view = self._get_active_view()
        if not view:
            raise RuntimeError("No active view in Krita to set brush")

        preset_name = data.get("preset")
        if preset_name:
            presets = self.app.resources("preset")
            target_preset = None
            if preset_name in presets:
                target_preset = presets[preset_name]
            else:
                p_lower = preset_name.lower()
                for k, v in presets.items():
                    if p_lower in k.lower():
                        target_preset = v
                        break
            if target_preset:
                view.setCurrentBrushPreset(target_preset)
            else:
                raise ValueError(f"Brush preset '{preset_name}' not found")

        if "size" in data and data["size"] is not None:
            view.setBrushSize(float(data["size"]))

        if "opacity" in data and data["opacity"] is not None:
            view.setPaintingOpacity(float(data["opacity"]))

        if "flow" in data and data["flow"] is not None:
            view.setPaintingFlow(float(data["flow"]))

        return {
            "updated": True,
            "preset": view.currentBrushPreset().name() if view.currentBrushPreset() else None,
            "size": view.brushSize(),
            "opacity": view.paintingOpacity(),
            "flow": view.paintingFlow()
        }

    def draw_line(self, data):
        """Paint a single line with pressure dynamics."""
        doc = self._get_active_doc(required=True)
        node = self._get_or_create_paint_layer(doc)

        x1 = int(round(float(data.get("x1", 0))))
        y1 = int(round(float(data.get("y1", 0))))
        x2 = int(round(float(data.get("x2", 0))))
        y2 = int(round(float(data.get("y2", 0))))
        p1 = float(data.get("pressure1", 1.0))
        p2 = float(data.get("pressure2", 1.0))
        stroke_style = data.get("stroke_style", "ForegroundColor") or "ForegroundColor"

        node.paintLine(QPoint(x1, y1), QPoint(x2, y2), p1, p2, stroke_style)
        doc.refreshProjection()
        return {"success": True, "layer": node.name()}

    def draw_lines(self, data):
        """Paint a sequence of points (polyline/stroke)."""
        doc = self._get_active_doc(required=True)
        node = self._get_or_create_paint_layer(doc)

        points = data.get("points", [])
        if len(points) < 2:
            return {"success": True, "segments": 0}

        stroke_style = data.get("stroke_style", "ForegroundColor") or "ForegroundColor"

        for i in range(len(points) - 1):
            pt_a = points[i]
            pt_b = points[i + 1]
            p_a = float(pt_a[2]) if len(pt_a) > 2 else 1.0
            p_b = float(pt_b[2]) if len(pt_b) > 2 else 1.0
            node.paintLine(
                QPoint(int(round(pt_a[0])), int(round(pt_a[1]))),
                QPoint(int(round(pt_b[0])), int(round(pt_b[1]))),
                p_a,
                p_b,
                stroke_style
            )

        doc.refreshProjection()
        return {"success": True, "segments": len(points) - 1, "layer": node.name()}

    def draw_rect(self, data):
        """Paint a rectangle with stroke and optional fill."""
        doc = self._get_active_doc(required=True)
        node = self._get_or_create_paint_layer(doc)

        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        w = float(data.get("width", 100))
        h = float(data.get("height", 100))
        stroke_style = data.get("stroke_style", "ForegroundColor") or "ForegroundColor"
        fill_style = data.get("fill_style", "None") or "None"

        rect = QRectF(x, y, w, h)
        node.paintRectangle(rect, stroke_style, fill_style)
        doc.refreshProjection()
        return {"success": True, "layer": node.name()}

    def draw_ellipse(self, data):
        """Paint an ellipse with stroke and optional fill."""
        doc = self._get_active_doc(required=True)
        node = self._get_or_create_paint_layer(doc)

        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        w = float(data.get("width", 100))
        h = float(data.get("height", 100))
        stroke_style = data.get("stroke_style", "ForegroundColor") or "ForegroundColor"
        fill_style = data.get("fill_style", "None") or "None"

        rect = QRectF(x, y, w, h)
        node.paintEllipse(rect, stroke_style, fill_style)
        doc.refreshProjection()
        return {"success": True, "layer": node.name()}

    def draw_svg(self, data):
        """Add SVG shapes to a vector layer."""
        doc = self._get_active_doc(required=True)
        svg_content = data.get("svg", "")
        if not svg_content:
            raise ValueError("Parameter 'svg' cannot be empty")

        layer_name = data.get("layer")
        target_node = None

        if layer_name:
            target_node = doc.nodeByName(layer_name)

        if not target_node or target_node.type() != "vectorlayer":
            # Find an existing vector layer
            for child in doc.rootNode().childNodes():
                if child.type() == "vectorlayer":
                    target_node = child
                    break

        if not target_node:
            # Create a new vector layer
            target_node = doc.createVectorLayer("Vector Shapes")
            doc.rootNode().addChildNode(target_node, None)

        doc.setActiveNode(target_node)
        shapes = target_node.addShapesFromSvg(svg_content)
        doc.refreshProjection()
        return {
            "success": True,
            "shapes_added": len(shapes),
            "layer": target_node.name()
        }

    def draw_pixels(self, data):
        """Write raw RGBA pixel data to a paint layer."""
        doc = self._get_active_doc(required=True)
        layer_name = data.get("layer")
        node = None
        if layer_name:
            node = doc.nodeByName(layer_name)
        if not node:
            node = self._get_or_create_paint_layer(doc)

        x = int(data.get("x", 0))
        y = int(data.get("y", 0))
        w = int(data.get("width", 0))
        h = int(data.get("height", 0))
        raw_input = data.get("data")

        if isinstance(raw_input, str):
            pixel_bytes = base64.b64decode(raw_input)
        elif isinstance(raw_input, (bytes, bytearray)):
            pixel_bytes = bytes(raw_input)
        else:
            raise ValueError("Pixel data must be base64 string or bytes")

        expected_size = w * h * 4
        if len(pixel_bytes) < expected_size:
            raise ValueError(f"Pixel data buffer too small: got {len(pixel_bytes)} bytes, expected {expected_size}")

        ok = node.setPixelData(pixel_bytes, x, y, w, h)
        doc.refreshProjection()
        return {"success": ok, "layer": node.name()}

    def eval_code(self, data):
        """Execute arbitrary Python code in Krita context."""
        code = data.get("script", "")
        if not code:
            return {"stdout": "", "stderr": "", "result": None, "error": "Empty script"}

        doc = self._get_active_doc(required=False)
        view = self._get_active_view()
        window = self.app.activeWindow()

        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        eval_env = {
            "Krita": Krita,
            "Application": self.app,
            "app": self.app,
            "doc": doc,
            "view": view,
            "window": window,
            "ManagedColor": ManagedColor,
            "controller": self,
        }

        result = None
        error = None

        try:
            try:
                compiled = compile(code, "<bridge_eval>", "eval")
                result = eval(compiled, eval_env)
            except SyntaxError:
                compiled = compile(code, "<bridge_eval>", "exec")
                exec(compiled, eval_env)
                result = eval_env.get("result", None)
        except Exception as e:
            error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        return {
            "stdout": stdout_capture.getvalue(),
            "stderr": stderr_capture.getvalue(),
            "result": repr(result) if result is not None else None,
            "error": error
        }

    def trigger_action(self, data):
        """Trigger a Krita registered action (e.g. undo, redo)."""
        action_name = data.get("action")
        if not action_name:
            raise ValueError("Parameter 'action' is required")

        act = self.app.action(action_name)
        if not act:
            raise ValueError(f"Action '{action_name}' not found in Krita")

        act.trigger()
        return {"triggered": True, "action": action_name}
