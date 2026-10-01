#!/usr/bin/env python3
"""
Showcase Drawing Demo for Krita AI Control.
Connects to Krita via KritaClient, creates a canvas, and paints
a multi-layered artistic mountain landscape under a starry night.
"""

import math
import os
import random
import subprocess
import sys
import time
from krita_client import KritaClient


def ensure_krita_running(client, timeout=25.0):
    """Check if Krita bridge is running; if not, attempt to launch Krita."""
    if client.is_connected():
        print("Connected to active Krita AI Controller bridge.")
        return True

    print("Krita bridge not detected. Launching Krita on DISPLAY=:0...")
    env = os.environ.copy()
    if "DISPLAY" not in env:
        env["DISPLAY"] = ":0"

    # Launch Krita detached in background
    subprocess.Popen(
        ["krita"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )

    print(f"Waiting for Krita bridge to initialize (up to {timeout}s)...")
    if client.wait_for_server(timeout=timeout):
        print("Krita bridge connected successfully!")
        return True
    else:
        print("Could not connect to Krita GUI bridge.")
        return False


def generate_sky_gradient(width, height):
    """Generate smooth RGBA gradient pixel buffer for night sky."""
    # Gradient from Deep Midnight Navy (#080C24) -> Twilight Indigo (#1C1842) -> Horizon Blue (#2D4263)
    c_top = (8, 12, 36)
    c_mid = (28, 24, 66)
    c_bot = (45, 66, 99)

    buf = bytearray(width * height * 4)
    idx = 0

    for y in range(height):
        factor = y / float(height)
        if factor < 0.5:
            t = factor / 0.5
            r = int(c_top[0] * (1 - t) + c_mid[0] * t)
            g = int(c_top[1] * (1 - t) + c_mid[1] * t)
            b = int(c_top[2] * (1 - t) + c_mid[2] * t)
        else:
            t = (factor - 0.5) / 0.5
            r = int(c_mid[0] * (1 - t) + c_bot[0] * t)
            g = int(c_mid[1] * (1 - t) + c_bot[1] * t)
            b = int(c_mid[2] * (1 - t) + c_bot[2] * t)

        # In Krita RGBA U8 pixel data:
        row_bytes = bytes([b, g, r, 255]) * width  # Note: Krita Integer RGBA channel order is BGRA
        buf[idx:idx + len(row_bytes)] = row_bytes
        idx += len(row_bytes)

    return bytes(buf)


def generate_celestial_svg(width, height, moon_cx=920, moon_cy=170):
    """Generate SVG markup for glowing crescent moon and constellation stars."""
    svg = [
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">',
        '  <defs>',
        '    <radialGradient id="moonGlow" cx="50%" cy="50%" r="50%">',
        '      <stop offset="0%" stop-color="#FFF3C4" stop-opacity="0.6"/>',
        '      <stop offset="40%" stop-color="#FFE082" stop-opacity="0.25"/>',
        '      <stop offset="100%" stop-color="#FFD54F" stop-opacity="0"/>',
        '    </radialGradient>',
        '    <filter id="softGlow">',
        '      <feGaussianBlur stdDeviation="3" result="coloredBlur"/>',
        '      <feMerge>',
        '        <feMergeNode in="coloredBlur"/>',
        '        <feMergeNode in="SourceGraphic"/>',
        '      </feMerge>',
        '    </filter>',
        '  </defs>',
        '  <!-- Moon Outer Atmosphere Glow -->',
        f'  <circle cx="{moon_cx}" cy="{moon_cy}" r="90" fill="url(#moonGlow)"/>',
        f'  <circle cx="{moon_cx}" cy="{moon_cy}" r="55" fill="url(#moonGlow)"/>',
        '  <!-- Crescent Moon -->',
        f'  <path d="M {moon_cx} {moon_cy - 38} '
        f'A 38 38 0 1 0 {moon_cx + 26} {moon_cy + 26} '
        f'A 32 32 0 1 1 {moon_cx} {moon_cy - 38} Z" '
        'fill="#FFFBE8" stroke="#FFE082" stroke-width="1"/>',
        '  <!-- Constellation Stars & Sparkles -->'
    ]

    random.seed(42)
    # Generate field of twinkling stars
    for _ in range(70):
        sx = random.randint(30, width - 40)
        sy = random.randint(20, int(height * 0.52))
        # Skip moon region
        if math.hypot(sx - moon_cx, sy - moon_cy) < 110:
            continue

        radius = round(random.uniform(0.8, 2.5), 1)
        opacity = round(random.uniform(0.4, 0.95), 2)
        svg.append(f'  <circle cx="{sx}" cy="{sy}" r="{radius}" fill="#FFFFFF" opacity="{opacity}"/>')

    # Add a few cross-sparkle large stars
    bright_stars = [(180, 110), (380, 75), (620, 140), (810, 95), (1060, 130), (280, 210)]
    for bx, by in bright_stars:
        svg.append(
            f'  <g transform="translate({bx},{by})">'
            f'    <line x1="-8" y1="0" x2="8" y2="0" stroke="#FFF9C4" stroke-width="1.2" opacity="0.8"/>'
            f'    <line x1="0" y1="-8" x2="0" y2="8" stroke="#FFF9C4" stroke-width="1.2" opacity="0.8"/>'
            f'    <circle cx="0" cy="0" r="2.2" fill="#FFFFFF"/>'
            f'  </g>'
        )

    svg.append('</svg>')
    return "\n".join(svg)


def draw_mountain_range(client, width, height):
    """Draw majestic mountain peaks with shading."""
    # Distant layer peaks
    distant_peaks = [
        (0, 480), (120, 410), (220, 460), (380, 370), (520, 440),
        (660, 350), (800, 430), (960, 380), (1080, 420), (1200, 470)
    ]

    # Paint distant ridge with smooth Catmull-Rom spline
    smooth_distant = client.smooth_curve(distant_peaks, num_segments=15)
    client.set_color(foreground="#162238")
    client.set_brush(size=14.0, opacity=0.9)
    client.draw_lines(smooth_distant)

    # Shading downwards from distant peaks
    client.set_brush(size=30.0, opacity=0.7)
    for pt in smooth_distant[::3]:
        x = pt[0]
        y = pt[1]
        client.draw_line(x, y, x + 15, y + 80, pressure1=0.8, pressure2=0.2)

    # Main foreground mountain ridge (sharper, prominent summits)
    peaks = [
        (0, 520, 0.8),
        (160, 440, 1.0),
        (260, 480, 0.7),
        (420, 310, 1.0),  # Summit 1
        (560, 420, 0.8),
        (720, 280, 1.0),  # Highest Summit 2
        (850, 390, 0.8),
        (1010, 340, 1.0), # Summit 3
        (1120, 430, 0.8),
        (1200, 510, 0.8)
    ]

    smooth_peaks = client.smooth_curve(peaks, num_segments=12)

    # Main ridge shadow side
    client.set_color(foreground="#0F1726")
    client.set_brush(size=12.0, opacity=1.0)
    client.draw_lines(smooth_peaks)

    # Fill mountain body
    client.set_brush(size=45.0, opacity=0.95)
    for pt in smooth_peaks[::2]:
        px, py = pt[0], pt[1]
        client.draw_line(px, py, px - 10, py + 160, pressure1=0.9, pressure2=0.4)

    # Snow cap highlights on sunward/moonlit face
    client.set_color(foreground="#C8D6E8")
    client.set_brush(size=6.0, opacity=0.85)

    summits = [(420, 310), (720, 280), (1010, 340)]
    for sx, sy in summits:
        # Snow crest left
        client.draw_line(sx, sy, sx - 45, sy + 55, pressure1=1.0, pressure2=0.3)
        client.draw_line(sx, sy, sx + 50, sy + 65, pressure1=1.0, pressure2=0.4)
        # Snow dabs
        client.draw_line(sx - 15, sy + 25, sx - 5, sy + 45, pressure1=0.7, pressure2=0.2)
        client.draw_line(sx + 10, sy + 30, sx + 25, sy + 55, pressure1=0.8, pressure2=0.3)


def draw_pine_tree(client, x, base_y, height=90, max_width=38):
    """Draw a stylized pine tree with trunk and tiered foliage branches."""
    # Trunk
    client.set_color(foreground="#0A140F")
    client.set_brush(size=4.5, opacity=0.95)
    client.draw_line(x, base_y, x, base_y - height, pressure1=1.0, pressure2=0.3)

    # Pine foliage tiers (dark evergreen #11281E to #1B3C2E)
    top_y = base_y - height
    tiers = 6
    client.set_color(foreground="#132B20")

    for i in range(tiers):
        tier_ratio = i / float(tiers)
        tier_y = top_y + tier_ratio * (height * 0.85)
        branch_w = (i + 1) * (max_width / tiers)

        client.set_brush(size=max(2.5, 5.0 - i * 0.4), opacity=0.9)
        # Left branches
        client.draw_line(x, tier_y, x - branch_w, tier_y + 8, pressure1=0.9, pressure2=0.3)
        client.draw_line(x, tier_y + 2, x - branch_w * 0.7, tier_y + 11, pressure1=0.7, pressure2=0.2)
        # Right branches
        client.draw_line(x, tier_y, x + branch_w, tier_y + 8, pressure1=0.9, pressure2=0.3)
        client.draw_line(x, tier_y + 2, x + branch_w * 0.7, tier_y + 11, pressure1=0.7, pressure2=0.2)


def draw_forest_and_lake(client, width, height):
    """Draw the pine forest along lake shoreline and gentle water reflections."""
    # Lake waterline base
    water_horizon = int(height * 0.65)

    # Deep lake water base
    client.set_color(foreground="#0C1424")
    client.set_brush(size=60.0, opacity=0.9)
    for y in range(water_horizon, height, 40):
        client.draw_line(0, y, width, y, pressure1=0.8, pressure2=0.8)

    # Shoreline ground ridge
    client.set_color(foreground="#080F0B")
    client.set_brush(size=25.0, opacity=1.0)
    shoreline = [
        (0, water_horizon + 10), (250, water_horizon - 5),
        (500, water_horizon + 15), (750, water_horizon - 10),
        (1000, water_horizon + 5), (1200, water_horizon - 8)
    ]
    client.draw_lines(client.smooth_curve(shoreline, num_segments=10))

    # Plant pine forest along shoreline
    tree_positions = [
        (35, 535, 75), (70, 530, 85), (110, 525, 95), (150, 535, 70), (190, 520, 105),
        (230, 530, 80), (320, 545, 65), (360, 540, 75),
        (820, 530, 80), (860, 520, 95), (900, 535, 75), (940, 515, 110),
        (980, 525, 85), (1020, 535, 70), (1060, 520, 100), (1110, 530, 85), (1160, 525, 95)
    ]

    for tx, ty, th in tree_positions:
        draw_pine_tree(client, tx, ty, height=th, max_width=th * 0.42)

    # Shimmering moon reflections on lake water
    moon_x = 920
    client.set_brush(size=5.0, opacity=0.6)
    client.set_color(foreground="#FFE082")

    for ry in range(water_horizon + 20, height - 40, 12):
        spread = 20 + (ry - water_horizon) * 0.8
        offset_x = random.randint(-8, 8)
        cx = moon_x + offset_x
        w_len = random.randint(int(spread * 0.5), int(spread * 1.4))
        client.draw_line(cx - w_len, ry, cx + w_len, ry, pressure1=0.2, pressure2=0.8)

    # Soft mist ripples across lake
    client.set_color(foreground="#3A506B")
    client.set_brush(size=8.0, opacity=0.35)
    for ry in range(water_horizon + 15, height - 20, 25):
        lx = random.randint(50, 400)
        client.draw_line(lx, ry, lx + random.randint(120, 280), ry, pressure1=0.4, pressure2=0.4)


def generate_signature_svg(width, height):
    """Generate elegant AI watermark & signature in bottom right corner."""
    x = width - 320
    y = height - 40
    svg = f"""<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <g transform="translate({x}, {y})">
    <rect x="-10" y="-22" width="310" height="34" rx="6" fill="#0A0E1A" opacity="0.7" stroke="#324B6E" stroke-width="1"/>
    <text x="10" y="0" font-family="DejaVu Sans, Liberation Sans, sans-serif" font-size="12" font-weight="bold" fill="#E2EDF8" letter-spacing="1">
      ANTIGRAVITY AI <tspan fill="#FFE082">✦</tspan> KRITA CONTROL
    </text>
  </g>
</svg>"""
    return svg


def main():
    print("=======================================================")
    print("    Krita AI Control & Drawing Bridge - Showcase Demo   ")
    print("=======================================================")

    client = KritaClient()

    # 1. Connect or launch Krita
    if not ensure_krita_running(client):
        print("ERROR: Unable to connect to Krita bridge.")
        print("Please run ./install_plugin.sh and launch Krita.")
        sys.exit(1)

    # 2. Check status and brushes
    status = client.status()
    print(f"Krita Version: {status.get('version')}")
    brushes = client.brushes()
    print(f"Found {len(brushes)} brush presets available in Krita.")

    # Select preferred pencil/brush
    brush_pref = "b) Basic-5 Size"
    if brush_pref not in brushes:
        for b in brushes:
            if "basic" in b.lower() or "pencil" in b.lower():
                brush_pref = b
                break
    print(f"Active drawing brush preset: '{brush_pref}'")

    # 3. Create document
    canvas_w = 1200
    canvas_h = 800
    print(f"\n[1/6] Creating canvas ({canvas_w}x{canvas_h})...")
    client.new_document(
        width=canvas_w,
        height=canvas_h,
        name="Antigravity_Scenic_Mountain",
        color_model="RGBA",
        color_depth="U8",
        resolution=120.0
    )
    time.sleep(0.5)

    # 4. Layer 1: Night Sky Gradient
    print("[2/6] Rendering Night Sky Gradient (Layer: 'Night Sky')...")
    client.new_layer("Night Sky", layer_type="paint")
    sky_pixels = generate_sky_gradient(canvas_w, canvas_h)
    client.draw_pixels(0, 0, canvas_w, canvas_h, sky_pixels, layer="Night Sky")

    # 5. Layer 2: Celestial & Stars
    print("[3/6] Generating Crescent Moon & Constellations (Layer: 'Celestial & Stars')...")
    client.new_layer("Celestial & Stars", layer_type="vector")
    moon_svg = generate_celestial_svg(canvas_w, canvas_h, moon_cx=920, moon_cy=170)
    client.draw_svg(moon_svg, layer="Celestial & Stars")

    # 6. Layer 3: Mountain Range
    print("[4/6] Painting Mountain Peaks & Snow Crests (Layer: 'Mountains')...")
    client.new_layer("Mountains", layer_type="paint")
    client.select_layer("Mountains")
    client.set_brush(preset=brush_pref)
    draw_mountain_range(client, canvas_w, canvas_h)

    # 7. Layer 4: Pine Forest & Alpine Lake
    print("[5/6] Planting Pine Forest & Lake Reflections (Layer: 'Forest & Lake')...")
    client.new_layer("Forest & Lake", layer_type="paint")
    client.select_layer("Forest & Lake")
    draw_forest_and_lake(client, canvas_w, canvas_h)

    # 8. Layer 5: Artist Signature
    print("[6/6] Affixing AI Artist Signature (Layer: 'AI Signature')...")
    client.new_layer("AI Signature", layer_type="vector")
    sig_svg = generate_signature_svg(canvas_w, canvas_h)
    client.draw_svg(sig_svg, layer="AI Signature")

    # 9. Canvas snapshot
    output_png = os.path.abspath("krita_ai_art.png")
    print(f"\nCapturing live canvas snapshot to: {output_png}...")
    png_bytes = client.snapshot(output_path=output_png)
    print(f"Snapshot captured successfully! Size: {len(png_bytes):,} bytes.")

    # Also save native Krita document (.kra)
    output_kra = os.path.abspath("krita_ai_art.kra")
    print(f"Saving native Krita file to: {output_kra}...")
    try:
        client.save(output_kra)
        print("Saved .kra file successfully!")
    except Exception as e:
        print(f"Notice: .kra save: {e}")

    print("\n=======================================================")
    print("    Showcase Demo Completed Successfully! 🎉          ")
    print(f"    View result: file://{output_png}                 ")
    print("=======================================================")


if __name__ == "__main__":
    main()
