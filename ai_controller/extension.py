"""
Krita Extension plugin managing AI Controller bridge lifecycle and Qt main-thread queue.
"""

import queue
import traceback
from PyQt6.QtCore import QTimer
from krita import Extension, Krita
from .controller import DrawingController
from .server import BridgeServer

_EXTENSION_INSTANCE = None


def get_extension():
    """Return singleton extension instance."""
    return _EXTENSION_INSTANCE


class AIControllerExtension(Extension):
    """Krita Extension running HTTP bridge and dispatching to Qt main thread."""

    def __init__(self, parent):
        super().__init__(parent)
        global _EXTENSION_INSTANCE
        _EXTENSION_INSTANCE = self

        self.command_queue = queue.Queue()
        self.controller = DrawingController()
        self.server = None
        self.timer = None
        self.docker = None
        self.default_port = 5678
        self._is_setup = False
        self.setup()

    def setup(self):
        """Called by Krita on startup or during initialization."""
        if self._is_setup:
            return
        self._is_setup = True

        # Initialize timer to process queued commands on main thread
        self.timer = QTimer()
        self.timer.setInterval(10)  # 10ms polling
        self.timer.timeout.connect(self._process_queue)
        self.timer.start()

        # Start bridge server
        try:
            self.start_server(self.default_port)
        except Exception as e:
            self.log(f"Failed to start bridge server on port {self.default_port}: {e}")

    def createActions(self, window):
        """Register menu actions for AI Controller."""
        action = window.createAction(
            "ai_controller_toggle",
            "Toggle AI Controller Server",
            "tools/scripts"
        )
        action.triggered.connect(self.toggle_server)

    def start_server(self, port=None):
        """Start the HTTP bridge server."""
        if port is None:
            port = self.default_port

        if self.server and self.server.is_running:
            return

        self.server = BridgeServer(
            host="127.0.0.1",
            port=port,
            command_queue=self.command_queue,
            controller=self.controller,
            logger_func=self.log
        )
        self.server.start()
        self.log(f"Server started on http://127.0.0.1:{port}")

        if self.docker:
            self.docker.update_server_status(True, port)

    def stop_server(self):
        """Stop the HTTP bridge server."""
        if self.server and self.server.is_running:
            port = self.server.port
            self.server.stop()
            self.server = None
            self.log(f"Server on port {port} stopped")

            if self.docker:
                self.docker.update_server_status(False)

    def toggle_server(self):
        """Toggle server running state."""
        if self.server and self.server.is_running:
            self.stop_server()
        else:
            self.start_server(self.default_port)

    def register_docker(self, docker):
        """Register the docker UI widget."""
        self.docker = docker
        if self.server:
            self.docker.update_server_status(self.server.is_running, self.server.port)
        else:
            self.docker.update_server_status(False, self.default_port)

    def log(self, message):
        """Log activity to terminal and docker panel."""
        print(f"[AIController] {message}")
        if self.docker:
            self.docker.append_log(message)

    def _process_queue(self):
        """Process tasks from HTTP threads safely on the Qt GUI thread."""
        max_batch = 50
        count = 0

        while count < max_batch:
            try:
                task = self.command_queue.get_nowait()
            except queue.Empty:
                break

            count += 1
            func = task.get("func")
            args = task.get("args", ())
            kwargs = task.get("kwargs", {})
            event = task.get("event")

            try:
                task["result"] = func(*args, **kwargs)
                task["success"] = True
            except Exception as e:
                task["error"] = f"{type(e).__name__}: {str(e)}"
                task["traceback"] = traceback.format_exc()
                task["success"] = False
                self.log(f"Command failed: {task['error']}")
            finally:
                if event:
                    event.set()
