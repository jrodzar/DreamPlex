#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate the frames of the "busy" spinner (a rotating accent-coloured arc)
shipped in each skin's images/busy/ folder and driven as a MultiPixmap by
DPH_ScreenHelper.startBusy().

Run on the dev machine (needs Pillow); the PNGs are committed to the repo.

    py -3 tools/make_spinner.py

Twelve frames sweeping a "comet" arc: the colour fades from opaque at the
head to transparent at the tail, so there are no round end-caps that read as
stray dots. One accent colour (the skin's amber #f0a30a); sizes match the
skin.xml widgets (72 px HD, 108 px FHD). Drawn 4x and downsampled.
"""
import math
import os

from PIL import Image, ImageDraw

FRAMES = 12
ACCENT = (240, 163, 10)           # #f0a30a - the skin accent (rgb)
ARC_DEG = 300                     # total sweep of the comet
SEGMENTS = 120                    # sub-arcs used to paint the alpha gradient
MIN_ALPHA = 25                    # tail opacity
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
    width = max(2, int(S * 0.11))
    m = width // 2 + 1
    box = [m, m, S - m, S - m]

    # paint the sweep as many short sub-arcs, opacity ramping tail->head, so
    # the colour fades out instead of ending in a round cap
    step = ARC_DEG / float(SEGMENTS)
    for i in range(SEGMENTS):
        frac = i / float(SEGMENTS - 1)          # 0 at tail, 1 at head
        alpha = int(MIN_ALPHA + frac * (255 - MIN_ALPHA))
        a0 = angle_deg + i * step
        # small overlap (+1.2 deg) keeps the ramp visually continuous
        d.arc(box, a0, a0 + step + 1.2, fill=ACCENT + (alpha,), width=width)

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
