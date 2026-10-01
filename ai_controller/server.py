"""
HTTP bridge server for Krita AI Controller.
Listens on 127.0.0.1:5678 and marshals requests to Krita's Qt main thread.
"""

import json
import socketserver
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer


class BridgeRequestHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests from AI or client scripts."""

    def _send_json(self, data, status_code=200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data, content_type="application/octet-stream", status_code=200):
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, message, status_code=400):
        self._send_json({"error": message, "status": "error"}, status_code=status_code)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        server = self.server

        try:
            if path == "/status":
                result = server.dispatch(server.controller.get_status)
                self._send_json(result)

            elif path == "/brushes":
                result = server.dispatch(server.controller.get_brushes)
                self._send_json(result)

            elif path == "/canvas/snapshot":
                bounds = None
                if all(k in query for k in ("x", "y", "w", "h")):
                    bounds = [
                        int(query["x"][0]),
                        int(query["y"][0]),
                        int(query["w"][0]),
                        int(query["h"][0])
                    ]
                png_bytes = server.dispatch(server.controller.get_snapshot, bounds=bounds)
                self._send_bytes(png_bytes, content_type="image/png")

            else:
                self._send_error(f"Endpoint '{path}' not found", status_code=404)

        except Exception as e:
            server.log(f"Error handling GET {path}: {e}")
            self._send_error(str(e), status_code=500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len) if content_len > 0 else b"{}"

        try:
            payload = json.loads(post_body.decode("utf-8")) if post_body else {}
        except Exception as e:
            self._send_error(f"Invalid JSON body: {e}", status_code=400)
            return

        server = self.server

        route_map = {
            "/document/new": server.controller.create_document,
            "/document/save": server.controller.save_document,
            "/layer/new": server.controller.create_layer,
            "/layer/select": server.controller.select_layer,
            "/tool/color": server.controller.set_color,
            "/tool/brush": server.controller.set_brush,
            "/draw/line": server.controller.draw_line,
            "/draw/lines": server.controller.draw_lines,
            "/draw/rect": server.controller.draw_rect,
            "/draw/ellipse": server.controller.draw_ellipse,
            "/draw/svg": server.controller.draw_svg,
            "/draw/pixels": server.controller.draw_pixels,
            "/eval": server.controller.eval_code,
            "/action/trigger": server.controller.trigger_action,
        }

        func = route_map.get(path)
        if not func:
            self._send_error(f"Endpoint '{path}' not found", status_code=404)
            return

        try:
            result = server.dispatch(func, payload)
            self._send_json(result)
        except Exception as e:
            server.log(f"Error handling POST {path}: {e}")
            self._send_error(str(e), status_code=500)

    def log_message(self, format, *args):
        # Suppress default noisy console logs
        pass


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server allowing concurrent snapshot and status queries."""
    daemon_threads = True
    allow_reuse_address = True


class BridgeServer:
    """Manages the lifecycle of the Krita AI Bridge HTTP server."""

    def __init__(self, host="127.0.0.1", port=5678, command_queue=None, controller=None, logger_func=None):
        self.host = host
        self.port = port
        self.command_queue = command_queue
        self.controller = controller
        self.logger_func = logger_func
        self.httpd = None
        self.thread = None
        self.is_running = False

    def log(self, msg):
        if self.logger_func:
            self.logger_func(msg)
        else:
            print(f"[BridgeServer] {msg}")

    def dispatch(self, func, *args, timeout=30.0, **kwargs):
        """Dispatch callable to Qt main thread via queue and wait for completion."""
        event = threading.Event()
        task = {
            "func": func,
            "args": args,
            "kwargs": kwargs,
            "event": event,
            "result": None,
            "success": False,
            "error": None,
            "traceback": None,
        }

        self.command_queue.put(task)
        completed = event.wait(timeout=timeout)
        if not completed:
            raise TimeoutError("Execution timed out waiting for Krita main thread")

        if not task["success"]:
            err_msg = task.get("error") or "Unknown error"
            tb = task.get("traceback") or ""
            raise RuntimeError(f"{err_msg}\n{tb}")

        return task["result"]

    def start(self):
        """Start server in background thread."""
        if self.is_running:
            return

        self.httpd = ThreadedHTTPServer((self.host, self.port), BridgeRequestHandler)
        self.httpd.dispatch = self.dispatch
        self.httpd.controller = self.controller
        self.httpd.log = self.log

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.is_running = True
        self.thread.start()

    def _run(self):
        try:
            self.httpd.serve_forever()
        except Exception as e:
            self.log(f"Server loop error: {e}")
        finally:
            self.is_running = False

    def stop(self):
        """Stop server gracefully."""
        if not self.is_running:
            return

        self.is_running = False
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
            self.thread = None
