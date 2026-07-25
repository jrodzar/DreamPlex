# -*- coding: utf-8 -*-
"""Report Listbox rows whose selection bar does not cover the whole row.

When a skin's `selectionPixmap` is shorter than the Listbox `itemHeight`,
enigma2 fills the leftover strip with its own default blue highlight, which
shows up as an ugly edge above/below the selected item (that was the FHD
menu bug fixed in v2.3.12). A `backgroundPixmap` on the Listbox hides it
whatever the mismatch, because enigma2 stretches it over the whole widget.

So a mismatch only matters when there is no backgroundPixmap.

This is a STATIC check: it says WHERE to look, it does not replace looking
at the screen. A Listbox built from code instead of from the XML is
invisible to it.

Exit code 1 if any Listbox is left uncovered.

Written for DreamPlex; the path resolution, the screen names and the
unbounded widget regex come back from the DreamFin fork, which runs the
same check (tools/audit_listbox_selection.py there).
"""

import glob
import os
import re
import sys

try:
	from PIL import Image
except ImportError:
	sys.exit("needs Pillow: py -3 -m pip install Pillow")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# no length limit on the body: a TemplatedMultiContent can run long, and
# capping it silently skipped those Listboxes (spotted by DreamFin)
WIDGET = re.compile(r'<widget\b[^>]*render="Listbox"[^>]*>.*?</widget>', re.S)
SELECTION = re.compile(r'selectionPixmap="([^"]+)"')
ITEM_HEIGHT = re.compile(r'"itemHeight"\s*:\s*(\d+)')
SCREEN = re.compile(r'<screen\b[^>]*name="([^"]+)"')


def screenAt(source, offset):
	"""Name of the last <screen> opened before this position."""
	name = "?"
	for match in SCREEN.finditer(source, 0, offset):
		name = match.group(1)

	return name


def resolvePixmap(skinDir, pixmapPath):
	"""Skin paths are absolute on the receiver, and may carry a subdirectory.

	Taking just the basename would happily read a different file of the same
	name (accent variants live in their own folder), and report it as fine.
	"""
	if "/skins/" in pixmapPath:
		tail = pixmapPath.split("/skins/", 1)[1]  # "<skin>/images/foo.png"
		parts = tail.split("/", 1)
		if len(parts) == 2:
			return os.path.join(skinDir, parts[1])

	return os.path.join(skinDir, "images", os.path.basename(pixmapPath))


def main():
	uncovered = []
	rows = []

	for skinXml in sorted(glob.glob(os.path.join(REPO_ROOT, "src", "skins", "*", "skin.xml"))):
		skinDir = os.path.dirname(skinXml)
		skinName = os.path.basename(skinDir)

		handle = open(skinXml, "rb")
		try:
			source = handle.read().decode("utf-8")
		finally:
			handle.close()

		for match in WIDGET.finditer(source):
			widget = match.group(0)

			selection = SELECTION.search(widget)
			height = ITEM_HEIGHT.search(widget)
			if not selection or not height:
				continue

			item = int(height.group(1))
			png = resolvePixmap(skinDir, selection.group(1))
			screen = screenAt(source, match.start())

			if not os.path.exists(png):
				rows.append((skinName, screen, item, "?", "MISSING PNG: " + png))
				uncovered.append(screen)
				continue

			pixmapHeight = Image.open(png).height
			hasBackground = "backgroundPixmap" in widget

			if pixmapHeight >= item:
				verdict = "ok"
			elif hasBackground:
				verdict = "gap %dpx, covered by backgroundPixmap" % (item - pixmapHeight)
			else:
				verdict = "*** GAP %dpx -> blue highlight ***" % (item - pixmapHeight)
				uncovered.append("%s/%s" % (skinName, screen))

			rows.append((skinName, screen, item, pixmapHeight, verdict))

	print("%-14s %-22s %-6s %-6s %s" % ("skin", "screen", "item", "png", "verdict"))
	print("-" * 96)
	for row in rows:
		print("%-14s %-22s %-6s %-6s %s" % row)

	print("\n%d Listbox checked" % len(rows))

	if uncovered:
		print("UNCOVERED: " + ", ".join(uncovered))
		return 1

	print("none left uncovered")
	return 0


if __name__ == "__main__":
	sys.exit(main())
