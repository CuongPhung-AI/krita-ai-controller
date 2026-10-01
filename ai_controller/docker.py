"""
Docker panel for AI Controller in Krita.
Provides visual feedback on server status and live activity logging.
"""

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QFrame
)
from krita import DockWidget
from .extension import get_extension


class AIControllerDocker(DockWidget):
    """Dockable panel showing AI Controller bridge status and activity logs."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Controller")

        # Main widget & layout
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        widget.setLayout(layout)

        # Header Title
        title_label = QLabel("AI Drawing & Control Bridge")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(10)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Status row
        status_frame = QFrame()
        status_frame.setFrameShape(QFrame.Shape.StyledPanel)
        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(6, 6, 6, 6)

        self.status_label = QLabel("Status: Initializing...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.addWidget(self.status_label)

        layout.addWidget(status_frame)

        # Control buttons
        btn_layout = QHBoxLayout()
        self.toggle_btn = QPushButton("Toggle Server")
        self.toggle_btn.clicked.connect(self._on_toggle_clicked)
        btn_layout.addWidget(self.toggle_btn)

        self.clear_btn = QPushButton("Clear Log")
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        btn_layout.addWidget(self.clear_btn)

        layout.addLayout(btn_layout)

        # Activity log label & text area
        log_label = QLabel("Activity Log:")
        layout.addWidget(log_label)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(500)
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(8)
        self.log_view.setFont(font)
        layout.addWidget(self.log_view)

        self.setWidget(widget)

        # Register with extension if loaded
        ext = get_extension()
        if ext:
            ext.register_docker(self)

    def canvasChanged(self, canvas):
        """Called by Krita when active canvas changes."""
        pass

    def update_server_status(self, is_running, port=5678):
        """Update the status indicator and toggle button text."""
        if is_running:
            self.status_label.setText(f"🟢 Running on 127.0.0.1:{port}")
            self.status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
            self.toggle_btn.setText("Stop Server")
        else:
            self.status_label.setText("🔴 Server Stopped")
            self.status_label.setStyleSheet("color: #c0392b; font-weight: bold;")
            self.toggle_btn.setText("Start Server")

    def append_log(self, text):
        """Append log message to the log viewer."""
        self.log_view.appendPlainText(text)
        # Scroll to bottom
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @pyqtSlot()
    def _on_toggle_clicked(self):
        ext = get_extension()
        if ext:
            ext.toggle_server()

    @pyqtSlot()
    def _on_clear_clicked(self):
        self.log_view.clear()
