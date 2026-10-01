"""
Comprehensive tests for Krita AI Control and Drawing Bridge.
Tests both client library utilities, headless execution, and live API endpoints.
"""

import math
import os
import unittest
from krita_client import KritaClient


class TestKritaClientUtilities(unittest.TestCase):
    """Test client utility methods that do not require live server."""

    def test_smooth_curve_basic(self):
        pts = [(0, 0), (100, 100)]
        curve = KritaClient.smooth_curve(pts, num_segments=10)
        self.assertGreater(len(curve), 2)
        # First and last point should match start and end
        self.assertEqual(curve[0][:2], [0, 0])
        self.assertEqual(curve[-1][:2], [100, 100])

    def test_smooth_curve_with_pressure(self):
        pts = [(0, 0, 0.2), (50, 80, 1.0), (100, 100, 0.5)]
        curve = KritaClient.smooth_curve(pts, num_segments=5)
        self.assertGreater(len(curve), 3)
        for pt in curve:
            self.assertEqual(len(pt), 3)
            # Pressure should be clamped between 0.05 and 1.0
            self.assertGreaterEqual(pt[2], 0.05)
            self.assertLessEqual(pt[2], 1.0)

    def test_execute_headless(self):
        code = """
from krita import Krita

def __main__(*args):
    app = Krita.instance()
    doc = app.createDocument(100, 100, 'HeadlessDoc', 'RGBA', 'U8', '', 120.0)
    print('DOCUMENT_CREATED:', doc.name(), doc.width(), doc.height(), flush=True)
    doc.close()
    return 0
"""
        res = KritaClient.execute_headless(code, timeout=20)
        self.assertEqual(res["exit_code"], 0, f"Headless execution failed: {res['stderr']}")
        self.assertIn("DOCUMENT_CREATED: HeadlessDoc 100 100", res["stdout"])


class TestKritaLiveBridge(unittest.TestCase):
    """Tests for live Krita bridge HTTP endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.client = KritaClient()
        cls.connected = cls.client.is_connected()
        if not cls.connected:
            print("Note: Krita bridge not running. Live tests will be skipped.")

    def test_01_status(self):
        if not self.connected:
            self.skipTest("Krita bridge is not running")
        status = self.client.status()
        self.assertIn("version", status)
        self.assertIn("documents_count", status)

    def test_02_brushes(self):
        if not self.connected:
            self.skipTest("Krita bridge is not running")
        brushes = self.client.brushes()
        self.assertIsInstance(brushes, list)
        self.assertGreater(len(brushes), 0)

    def test_03_create_document_and_layers(self):
        if not self.connected:
            self.skipTest("Krita bridge is not running")
        doc_res = self.client.new_document(width=500, height=400, name="TestBridgeCanvas")
        self.assertTrue(doc_res.get("created"))

        # Create a paint layer
        p_res = self.client.new_layer("PaintTest", layer_type="paint")
        self.assertTrue(p_res.get("created"))
        self.assertEqual(p_res.get("type"), "paintlayer")

        # Create a vector layer
        v_res = self.client.new_layer("VectorTest", layer_type="vector")
        self.assertTrue(v_res.get("created"))
        self.assertEqual(v_res.get("type"), "vectorlayer")

    def test_04_drawing_primitives(self):
        if not self.connected:
            self.skipTest("Krita bridge is not running")
        self.client.select_layer("PaintTest")
        self.client.set_color(foreground="#FF0055", background="#001122")
        self.client.set_brush(size=10.0, opacity=0.8)

        # Draw line
        line_res = self.client.draw_line(10, 10, 100, 100, pressure1=0.5, pressure2=1.0)
        self.assertTrue(line_res.get("success"))

        # Draw polyline
        pts = [(20, 20, 0.4), (60, 40, 0.8), (120, 30, 1.0)]
        lines_res = self.client.draw_lines(pts)
        self.assertTrue(lines_res.get("success"))

        # Draw rect & ellipse
        rect_res = self.client.draw_rect(50, 50, 80, 60)
        self.assertTrue(rect_res.get("success"))

        ellipse_res = self.client.draw_ellipse(150, 50, 70, 70)
        self.assertTrue(ellipse_res.get("success"))

        # Draw pixels
        pixel_bytes = bytes([255, 128, 0, 255] * 100) # 10x10 orange
        px_res = self.client.draw_pixels(200, 200, 10, 10, pixel_bytes)
        self.assertTrue(px_res.get("success"))

    def test_05_svg_vector(self):
        if not self.connected:
            self.skipTest("Krita bridge is not running")
        svg = '<svg><polygon points="100,10 40,198 190,78 10,78 160,198" fill="gold"/></svg>'
        svg_res = self.client.draw_svg(svg, layer="VectorTest")
        self.assertTrue(svg_res.get("success"))
        self.assertGreaterEqual(svg_res.get("shapes_added", 0), 1)

    def test_06_eval_and_action(self):
        if not self.connected:
            self.skipTest("Krita bridge is not running")
        eval_res = self.client.eval("2 + 2")
        self.assertEqual(eval_res.get("result"), "4")

        # Action trigger test
        act_res = self.client.trigger_action("edit_undo")
        self.assertTrue(act_res.get("triggered"))

    def test_07_canvas_snapshot(self):
        if not self.connected:
            self.skipTest("Krita bridge is not running")
        out_file = "/tmp/test_snapshot.png"
        if os.path.exists(out_file):
            os.remove(out_file)
        png_bytes = self.client.snapshot(output_path=out_file)
        self.assertGreater(len(png_bytes), 0)
        self.assertTrue(os.path.exists(out_file))
        # PNG signature check (bytes 0-7: 89 50 4E 47 0D 0A 1A 0A)
        self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_08_silent_save_kra_and_export_png(self):
        if not self.connected:
            self.skipTest("Krita bridge is not running")
        kra_path = "/tmp/test_bridge_save.kra"
        png_path = "/tmp/test_bridge_save.png"
        for p in (kra_path, png_path):
            if os.path.exists(p):
                os.remove(p)

        # 1. Save native .kra format
        res_kra = self.client.save(kra_path)
        self.assertTrue(res_kra.get("saved"))
        self.assertTrue(os.path.exists(kra_path))
        self.assertGreater(os.path.getsize(kra_path), 0)

        # 2. Export raster .png format
        res_png = self.client.save(png_path)
        self.assertTrue(res_png.get("saved"))
        self.assertTrue(os.path.exists(png_path))
        self.assertGreater(os.path.getsize(png_path), 0)
        with open(png_path, "rb") as f:
            header = f.read(8)
        self.assertEqual(header, b"\x89PNG\r\n\x1a\n")

        # 3. Test overwrite (ensuring no confirmation popup blocks execution)
        res_kra_ow = self.client.save(kra_path)
        self.assertTrue(res_kra_ow.get("saved"))

        res_png_ow = self.client.save(png_path)
        self.assertTrue(res_png_ow.get("saved"))

        # 4. Re-save existing document without specifying path
        res_resave = self.client.save()
        self.assertTrue(res_resave.get("saved"))
        self.assertEqual(res_resave.get("path"), os.path.abspath(kra_path))

        # 5. Export with export_options
        opt_png = "/tmp/test_bridge_options.png"
        if os.path.exists(opt_png):
            os.remove(opt_png)
        res_opt = self.client.save(opt_png, export_options={"compression": 9, "alpha": True})
        self.assertTrue(res_opt.get("saved"))
        self.assertTrue(os.path.exists(opt_png))
        os.remove(opt_png)

        # 6. Tilde path expansion
        tilde_png = "~/test_bridge_tilde.png"
        expanded_png = os.path.expanduser(tilde_png)
        if os.path.exists(expanded_png):
            os.remove(expanded_png)
        res_tilde = self.client.save(tilde_png)
        self.assertTrue(res_tilde.get("saved"))
        self.assertTrue(os.path.exists(expanded_png))
        os.remove(expanded_png)

        # 7. Verify batchmode restored on both app and document
        app_batch = self.client.eval("Krita.instance().batchmode()").get("result")
        doc_batch = self.client.eval("Krita.instance().activeDocument().batchmode()").get("result")
        self.assertEqual(app_batch, "False")
        self.assertEqual(doc_batch, "False")

    def test_09_save_error_recovery_and_cleanup(self):
        if not self.connected:
            self.skipTest("Krita bridge is not running")

        # 1. Creating new untitled document and saving without path should fail
        self.client.new_document(width=200, height=200, name="UntitledBlankCanvas")
        with self.assertRaises(RuntimeError) as ctx:
            self.client.save()
        self.assertIn("Parameter 'path' is required", str(ctx.exception))

        # 2. Saving to an unwritable directory should fail and restore batchmode
        with self.assertRaises(RuntimeError):
            self.client.save("/proc/invalid_path.png")

        app_batch = self.client.eval("Krita.instance().batchmode()").get("result")
        doc_batch = self.client.eval("Krita.instance().activeDocument().batchmode()").get("result")
        self.assertEqual(app_batch, "False")
        self.assertEqual(doc_batch, "False")


if __name__ == "__main__":
    unittest.main(verbosity=2)
