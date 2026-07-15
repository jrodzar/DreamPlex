#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate the frames of the "busy" spinner (a rotating accent-coloured arc)
shipped in each skin's images/busy/ folder and driven as a MultiPixmap by
DPH_ScreenHelper.startBusy().

Run on the dev machine (needs Pillow); the PNGs are committed to the repo.

    py -3 tools/make_spinner.py

Twelve frames, each the previous rotated by 360/12 degrees, drawn 4x and
downsampled for clean edges. One accent colour (the skin's amber #f0a30a);
sizes match the skin.xml widgets (72 px HD, 108 px FHD).
"""
import math
import os

from PIL import Image, ImageDraw

FRAMES = 12
ACCENT = (240, 163, 10, 255)      # #f0a30a - the skin accent
TRACK = (150, 150, 150, 60)       # faint full ring behind the arc
ARC_DEG = 270                     # sweep of the moving arc
SUPERSAMPLE = 4

# skin folder -> spinner pixel size (matches the <widget name="busy"> size)
TARGETS = {
    "default": 72,
    "BlueMod": 72,
    "default_FHD": 108,
    "BlueMod_FHD": 108,
}

HERE = os.path.dirname(os.path.abspath(__file__))
SKINS = os.path.join(HERE, "..", "src", "skins")


def make_frame(size, angle_deg):
    S = size * SUPERSAMPLE
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    width = max(2, int(S * 0.12))
    m = width // 2 + 1
    box = [m, m, S - m, S - m]
    # faint full track
    d.arc(box, 0, 360, fill=TRACK, width=width)
    # moving accent arc
    start = angle_deg
    end = angle_deg + ARC_DEG
    d.arc(box, start, end, fill=ACCENT, width=width)
    # round caps at both ends of the accent arc
    r = (S - 2 * m) / 2.0
    cx = cy = S / 2.0
    for ang in (start, end):
        a = math.radians(ang)
        x = cx + r * math.cos(a)
        y = cy + r * math.sin(a)
        d.ellipse([x - width / 2.0, y - width / 2.0,
                   x + width / 2.0, y + width / 2.0], fill=ACCENT)
    return im.resize((size, size), Image.LANCZOS)


def main():
    total = 0
    for skin, size in TARGETS.items():
        out = os.path.join(SKINS, skin, "images", "busy")
        if not os.path.isdir(os.path.dirname(out)):
            print("skip (no images dir): " + skin)
            continue
        if not os.path.isdir(out):
            os.makedirs(out)
        for i in range(FRAMES):
            frame = make_frame(size, -90 + i * (360.0 / FRAMES))
            frame.save(os.path.join(out, "busy_%02d.png" % i), optimize=True)
            total += 1
        print("%-14s %2d frames @ %dpx -> %s" % (skin, FRAMES, size, out))
    print("done, %d PNGs" % total)


if __name__ == "__main__":
    main()
