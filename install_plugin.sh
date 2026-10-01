#!/usr/bin/env bash
set -e

# Base directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_PLUGIN_DIR="$SCRIPT_DIR/ai_controller"
TARGET_PYKRITA_DIR="$HOME/.local/share/krita/pykrita"
KRITARC="$HOME/.config/kritarc"

echo "================================================"
echo "Installing Krita AI Controller Plugin"
echo "================================================"

# 1. Create target pykrita directory if needed
mkdir -p "$TARGET_PYKRITA_DIR"

# 2. Copy desktop file
echo "Copying ai_controller.desktop to $TARGET_PYKRITA_DIR/..."
cp -f "$SOURCE_PLUGIN_DIR/ai_controller.desktop" "$TARGET_PYKRITA_DIR/ai_controller.desktop"

# 3. Copy plugin package directory
echo "Copying ai_controller module to $TARGET_PYKRITA_DIR/ai_controller..."
rm -rf "$TARGET_PYKRITA_DIR/ai_controller"
mkdir -p "$TARGET_PYKRITA_DIR/ai_controller"
cp -rf "$SOURCE_PLUGIN_DIR"/* "$TARGET_PYKRITA_DIR/ai_controller/"

# 4. Enable plugin in ~/.config/kritarc
echo "Configuring $KRITARC..."
mkdir -p "$(dirname "$KRITARC")"
touch "$KRITARC"

python3 - <<'EOF'
import os

kritarc_path = os.path.expanduser("~/.config/kritarc")
setting_key = "enable_ai_controller=true"
group_header = "[python]"

with open(kritarc_path, "r", encoding="utf-8", errors="replace") as f:
    content = f.read()

lines = content.splitlines()

# Check if already enabled
already_enabled = any(line.strip() == setting_key for line in lines)
if already_enabled:
    print("Plugin is already enabled in kritarc.")
else:
    python_section_idx = -1
    for i, line in enumerate(lines):
        if line.strip() == group_header:
            python_section_idx = i
            break

    if python_section_idx != -1:
        # Insert under existing [python] section
        lines.insert(python_section_idx + 1, setting_key)
        print("Added enable_ai_controller=true to existing [python] section.")
    else:
        # Append new [python] section
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.append(group_header)
        lines.append(setting_key)
        print("Created [python] section with enable_ai_controller=true.")

    with open(kritarc_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
EOF

echo "================================================"
echo "Installation complete!"
echo "Files installed:"
echo "  - $TARGET_PYKRITA_DIR/ai_controller.desktop"
echo "  - $TARGET_PYKRITA_DIR/ai_controller/"
echo "Bridge server will start on http://127.0.0.1:5678 when Krita starts."
echo "================================================"
