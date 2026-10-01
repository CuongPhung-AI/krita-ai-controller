# Krita AI Controller

A Krita plugin and client library to control Krita with code.

## Architecture

This project has two components:
- `ai_controller`: A Python plugin inside Krita. It runs an HTTP bridge on `127.0.0.1:5678`.
- `krita_client.py`: A Python client that sends HTTP commands to the bridge.

The bridge uses a Qt timer to run commands on the main Krita thread.

## Requirements

- Krita 5.x or newer
- Python 3.10 or newer
- PyQt6

## Installation

Run the install script:

```bash
./install_plugin.sh
```

Then start Krita. The plugin starts the HTTP server automatically.

## Usage

Use `krita_client.py` in your Python script:

```python
from krita_client import KritaClient

client = KritaClient()

# Check connection
if client.is_connected():
    print("Connected to Krita")

# Create a canvas
client.new_document(width=1920, height=1080, name="AI Canvas")

# Add a layer
client.new_layer("Sketch", layer_type="paint")

# Set brush and color
client.set_color(foreground="#FF0000")
client.set_brush(size=5.0, opacity=1.0)

# Draw a line
client.draw_line(100, 100, 500, 500)

# Save a snapshot
client.snapshot(output_path="preview.png")
```

## Capabilities

- Thread-safe command queue with Qt timers.
- Document and layer management.
- Canvas snapshots in PNG format.
- Brush preset and color control.
- Vector shape and pixel painting.
