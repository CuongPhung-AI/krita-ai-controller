"""
Krita AI Client Library.
Provides programmatic control over Krita via the AI Controller bridge server
with support for live GUI interactions and headless kritarunner execution.
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


class KritaClient:
    """Client library for interacting with Krita via the AI Controller bridge."""

    def __init__(self, host="127.0.0.1", port=5678, timeout=30.0):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout

    def _request(self, endpoint, method="GET", payload=None):
        url = f"{self.base_url}{endpoint}"
        headers = {}
        data = None

        if payload is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
            data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                content_type = resp.headers.get("Content-Type", "")
                content = resp.read()

                if "application/json" in content_type:
                    return json.loads(content.decode("utf-8"))
                return content
        except urllib.error.HTTPError as e:
            err_msg = str(e)
            try:
                err_data = json.loads(e.read().decode("utf-8"))
                if isinstance(err_data, dict) and "error" in err_data:
                    err_msg = err_data["error"]
            except Exception:
                pass
            raise RuntimeError(f"Krita Bridge Error ({e.code}): {err_msg}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Failed to connect to Krita AI Controller on {self.base_url}: {e}.\n"
                f"Ensure Krita is running with the ai_controller plugin installed and enabled."
            ) from e

    def is_connected(self):
        """Check if Krita bridge server is alive."""
        try:
            resp = self._request("/status", method="GET")
            return isinstance(resp, dict) and "version" in resp
        except Exception:
            return False

    def wait_for_server(self, timeout=15.0, interval=0.5):
        """Poll until server is available or timeout expires."""
        start = time.time()
        while time.time() - start < timeout:
            if self.is_connected():
                return True
            time.sleep(interval)
        return False

    def status(self):
        """Get Krita session status, active document, layers, and brush info."""
        return self._request("/status", method="GET")

    def brushes(self):
        """Get list of available brush preset names."""
        res = self._request("/brushes", method="GET")
        return res.get("presets", [])

    def snapshot(self, output_path=None, bounds=None):
        """
        Capture canvas projection as PNG image.
        If output_path is provided, saves to disk.
        Returns raw PNG bytes.
        """
        endpoint = "/canvas/snapshot"
        if bounds and len(bounds) == 4:
            x, y, w, h = bounds
            endpoint += f"?x={x}&y={y}&w={w}&h={h}"

        png_bytes = self._request(endpoint, method="GET")

        if output_path:
            out_dir = os.path.dirname(output_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(png_bytes)

        return png_bytes

    def new_document(self, width=1920, height=1080, name="AI Canvas",
                     color_model="RGBA", color_depth="U8", resolution=120.0):
        """Create a new document."""
        payload = {
            "width": width,
            "height": height,
            "name": name,
            "color_model": color_model,
            "color_depth": color_depth,
            "resolution": resolution
        }
        return self._request("/document/new", method="POST", payload=payload)

    def save(self, path=None, export_options=None):
        """
        Save active document to given path or re-save existing document.
        Runs silently in batchmode without modal dialogs.
        """
        payload = {}
        if path is not None:
            payload["path"] = os.path.abspath(os.path.expanduser(os.path.expandvars(str(path))))
        if export_options is not None:
            payload["export_options"] = export_options
        return self._request("/document/save", method="POST", payload=payload)

    def new_layer(self, name, layer_type="paint", parent=None, above=None):
        """Create a new layer ('paint', 'vector', or 'group')."""
        payload = {
            "name": name,
            "type": layer_type,
            "parent": parent,
            "above": above
        }
        return self._request("/layer/new", method="POST", payload=payload)

    def select_layer(self, name):
        """Select an existing layer by name."""
        payload = {"name": name}
        return self._request("/layer/select", method="POST", payload=payload)

    def set_color(self, foreground=None, background=None):
        """
        Set foreground and/or background color.
        Accepts hex string ('#FF5500'), RGB tuple (255, 85, 0), or RGBA tuple (255, 85, 0, 255).
        """
        payload = {}
        if foreground is not None:
            payload["foreground"] = foreground
        if background is not None:
            payload["background"] = background
        return self._request("/tool/color", method="POST", payload=payload)

    def set_brush(self, preset=None, size=None, opacity=None, flow=None):
        """Set active brush preset, size (px), opacity (0..1), and flow (0..1)."""
        payload = {}
        if preset is not None:
            payload["preset"] = preset
        if size is not None:
            payload["size"] = size
        if opacity is not None:
            payload["opacity"] = opacity
        if flow is not None:
            payload["flow"] = flow
        return self._request("/tool/brush", method="POST", payload=payload)

    def draw_line(self, x1, y1, x2, y2, pressure1=1.0, pressure2=1.0, stroke_style="ForegroundColor"):
        """Paint a line with pressure dynamics."""
        payload = {
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "pressure1": pressure1,
            "pressure2": pressure2,
            "stroke_style": stroke_style
        }
        return self._request("/draw/line", method="POST", payload=payload)

    def draw_lines(self, points, stroke_style="ForegroundColor"):
        """
        Paint a sequence of points (polyline/stroke).
        points: list of [x, y] or [x, y, pressure].
        """
        payload = {
            "points": points,
            "stroke_style": stroke_style
        }
        return self._request("/draw/lines", method="POST", payload=payload)

    def draw_rect(self, x, y, width, height, stroke_style="ForegroundColor", fill_style="None"):
        """Paint a rectangle."""
        payload = {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "stroke_style": stroke_style,
            "fill_style": fill_style
        }
        return self._request("/draw/rect", method="POST", payload=payload)

    def draw_ellipse(self, x, y, width, height, stroke_style="ForegroundColor", fill_style="None"):
        """Paint an ellipse."""
        payload = {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "stroke_style": stroke_style,
            "fill_style": fill_style
        }
        return self._request("/draw/ellipse", method="POST", payload=payload)

    def draw_circle(self, cx, cy, radius, stroke_style="ForegroundColor", fill_style="None"):
        """Convenience method to paint a circle."""
        return self.draw_ellipse(
            cx - radius,
            cy - radius,
            radius * 2,
            radius * 2,
            stroke_style=stroke_style,
            fill_style=fill_style
        )

    def draw_svg(self, svg_content, layer=None):
        """Add SVG shapes or paths to a vector layer."""
        payload = {
            "svg": svg_content,
            "layer": layer
        }
        return self._request("/draw/svg", method="POST", payload=payload)

    def draw_pixels(self, x, y, width, height, data, layer=None):
        """
        Write raw pixel buffer to a paint layer.
        data: raw bytes or base64 string (RGBA, 4 bytes per pixel).
        """
        if isinstance(data, (bytes, bytearray)):
            data_b64 = base64.b64encode(data).decode("ascii")
        elif isinstance(data, str):
            data_b64 = data
        else:
            raise TypeError("data must be bytes, bytearray, or base64 str")

        payload = {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "data": data_b64,
            "layer": layer
        }
        return self._request("/draw/pixels", method="POST", payload=payload)

    def eval(self, script):
        """Evaluate Python script inside Krita."""
        payload = {"script": script}
        return self._request("/eval", method="POST", payload=payload)

    def trigger_action(self, action_name):
        """Trigger a Krita action (e.g. 'edit_undo', 'edit_redo', 'clear')."""
        payload = {"action": action_name}
        return self._request("/action/trigger", method="POST", payload=payload)

    # Drawing helper utilities
    @staticmethod
    def smooth_curve(control_points, num_segments=20):
        """
        Generate smooth interpolated points from control points using Catmull-Rom spline.
        control_points: list of (x, y) or (x, y, p)
        """
        if len(control_points) < 2:
            return control_points

        # Pad ends
        pts = [control_points[0]] + list(control_points) + [control_points[-1]]
        has_pressure = len(control_points[0]) > 2

        curve_points = []
        for i in range(1, len(pts) - 2):
            p0 = pts[i - 1]
            p1 = pts[i]
            p2 = pts[i + 1]
            p3 = pts[i + 2]

            for t_step in range(num_segments):
                t = t_step / float(num_segments)
                t2 = t * t
                t3 = t2 * t

                # Catmull-Rom matrix basis
                x = 0.5 * (
                    (2 * p1[0]) +
                    (-p0[0] + p2[0]) * t +
                    (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                    (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
                )
                y = 0.5 * (
                    (2 * p1[1]) +
                    (-p0[1] + p2[1]) * t +
                    (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                    (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
                )
                if has_pressure:
                    pres0 = p0[2] if len(p0) > 2 else 1.0
                    pres1 = p1[2] if len(p1) > 2 else 1.0
                    pres2 = p2[2] if len(p2) > 2 else 1.0
                    pres3 = p3[2] if len(p3) > 2 else 1.0
                    p = 0.5 * (
                        (2 * pres1) +
                        (-pres0 + pres2) * t +
                        (2 * pres0 - 5 * pres1 + 4 * pres2 - pres3) * t2 +
                        (-pres0 + 3 * pres1 - 3 * pres2 + pres3) * t3
                    )
                    curve_points.append([round(x, 1), round(y, 1), max(0.05, min(1.0, round(p, 3)))])
                else:
                    curve_points.append([round(x, 1), round(y, 1)])

        curve_points.append(list(control_points[-1]))
        return curve_points

    @staticmethod
    def execute_headless(script_file_or_code, function="__main__", timeout=60):
        """
        Execute python script headlessly via kritarunner.
        """
        temp_file = None
        if os.path.exists(script_file_or_code):
            script_path = os.path.abspath(script_file_or_code)
        else:
            temp_file = "/tmp/krita_temp_headless.py"
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(script_file_or_code)
            script_path = temp_file

        dirname = os.path.dirname(script_path)
        basename = os.path.splitext(os.path.basename(script_path))[0]

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{dirname}:{existing_pythonpath}" if existing_pythonpath else dirname

        cmd = ["kritarunner", "-s", basename, "-f", function]
        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass


def main():
    parser = argparse.ArgumentParser(description="Krita AI Controller CLI Client")
    parser.add_argument("--host", default="127.0.0.1", help="Bridge host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5678, help="Bridge port (default: 5678)")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # status
    subparsers.add_parser("status", help="Get Krita status")

    # brushes
    subparsers.add_parser("brushes", help="List brush presets")

    # snapshot
    snap_parser = subparsers.add_parser("snapshot", help="Capture canvas projection")
    snap_parser.add_argument("output", help="Path to save PNG snapshot")

    # eval
    eval_parser = subparsers.add_parser("eval", help="Evaluate Python code in Krita")
    eval_parser.add_argument("code", help="Python code to evaluate")

    # action
    action_parser = subparsers.add_parser("action", help="Trigger Krita action")
    action_parser.add_argument("name", help="Action name (e.g. edit_undo)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    client = KritaClient(host=args.host, port=args.port)

    try:
        if args.command == "status":
            res = client.status()
            print(json.dumps(res, indent=2))
        elif args.command == "brushes":
            b = client.brushes()
            print(f"Total brushes: {len(b)}")
            for name in b:
                print(f"  - {name}")
        elif args.command == "snapshot":
            client.snapshot(args.output)
            print(f"Canvas snapshot saved to {args.output}")
        elif args.command == "eval":
            res = client.eval(args.code)
            print(json.dumps(res, indent=2))
        elif args.command == "action":
            res = client.trigger_action(args.name)
            print(json.dumps(res, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
