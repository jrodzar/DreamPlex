# -*- coding: utf-8 -*-
"""Build an installable DreamPlex IPK without any external tooling.

Produces the exact layout opkg-build (and therefore the OpenATV feed)
ships: an outer tar.gz containing ./debian-binary, ./control.tar.gz and
./data.tar.gz. Runs on a bare Python 3 (or 2.7) interpreter - no ar, no
msgfmt, no opkg-utils needed - so the package can be built on Windows.

The po/ catalogs are compiled to locale/<lang>/LC_MESSAGES/DreamPlex.mo
with a small pure-python msgfmt replacement.

Usage:  py -3 tools/build_ipk.py [--outdir dist]
"""

from __future__ import print_function

import argparse
import io
import os
import re
import struct
import sys
import tarfile
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, "src")
PO_DIR = os.path.join(REPO_ROOT, "po")
CONTROL_DIR = os.path.join(REPO_ROOT, "CONTROL")

PLUGIN_TARGET = "usr/lib/enigma2/python/Plugins/Extensions/DreamPlex"

# files installed from the src/ root next to the python modules
ROOT_EXTRA_FILES = [
	"keymap.xml",
	"maintainer.info",
	"pluginLogo.png",
	"pluginLogoHD.png",
	"LICENSE.txt",
]

EXCLUDED_NAMES = ("Makefile.am", "Makefile.in", "Makefile")


#===============================================================================
# .po -> .mo (pure python msgfmt replacement)
#===============================================================================

_UNESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


def _po_unescape(value):
	return re.sub(r'\\([nrt"\\])', lambda m: _UNESCAPES[m.group(1)], value)


def parse_po(path):
	"""Parse a po file into {key_bytes: value_bytes} for the mo writer."""
	catalog = {}
	entry = None

	def flush(current):
		if current is None or current.get("msgid") is None:
			return
		if current.get("fuzzy") and current["msgid"] != "":
			return  # like msgfmt: fuzzy entries are dropped

		msgstrs = current["msgstr"]
		if not any(msgstrs.values()):
			return  # untranslated

		key = current["msgid"]
		if current.get("msgid_plural") is not None:
			key = key + "\x00" + current["msgid_plural"]
			value = "\x00".join(msgstrs[i] for i in sorted(msgstrs))
		else:
			value = msgstrs.get(0, "")

		if current.get("msgctxt") is not None:
			key = current["msgctxt"] + "\x04" + key

		catalog[key.encode("utf-8")] = value.encode("utf-8")

	fd = io.open(path, "r", encoding="utf-8")
	try:
		lines = fd.read().splitlines()
	finally:
		fd.close()

	section = None
	for rawLine in lines + [""]:
		line = rawLine.strip()

		if not line:
			flush(entry)
			entry = None
			section = None
			continue

		if line.startswith("#"):
			if line.startswith("#,") and "fuzzy" in line:
				if entry is None:
					entry = {"msgid": None, "msgstr": {}, "fuzzy": True}
				else:
					entry["fuzzy"] = True
			continue

		match = re.match(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[(\d+)\])?)\s+"(.*)"$', line)
		if match:
			keyword, plural_index, text = match.group(1), match.group(2), _po_unescape(match.group(3))

			if keyword == "msgid":
				if entry is not None and entry.get("msgid") is not None:
					flush(entry)
					entry = None
				if entry is None:
					entry = {"msgid": None, "msgstr": {}, "fuzzy": False}
				entry["msgid"] = text
				section = ("msgid",)
			elif keyword == "msgctxt":
				if entry is not None and entry.get("msgid") is not None:
					flush(entry)
					entry = None
				if entry is None:
					entry = {"msgid": None, "msgstr": {}, "fuzzy": False}
				entry["msgctxt"] = text
				section = ("msgctxt",)
			elif keyword == "msgid_plural":
				entry["msgid_plural"] = text
				section = ("msgid_plural",)
			else:  # msgstr / msgstr[N]
				index = int(plural_index) if plural_index is not None else 0
				entry["msgstr"][index] = text
				section = ("msgstr", index)
			continue

		if line.startswith('"') and line.endswith('"') and entry is not None and section:
			text = _po_unescape(line[1:-1])
			if section[0] == "msgid":
				entry["msgid"] += text
			elif section[0] == "msgctxt":
				entry["msgctxt"] += text
			elif section[0] == "msgid_plural":
				entry["msgid_plural"] += text
			else:
				entry["msgstr"][section[1]] += text

	return catalog


def compile_mo(catalog):
	"""Binary GNU .mo writer (same layout as Tools/i18n/msgfmt.py)."""
	keys = sorted(catalog)
	ids = b""
	strs = b""
	koffsets = []
	voffsets = []

	for key in keys:
		value = catalog[key]
		koffsets.append((len(key), len(ids)))
		voffsets.append((len(value), len(strs)))
		ids += key + b"\x00"
		strs += value + b"\x00"

	n = len(keys)
	keystart = 7 * 4 + 16 * n
	valuestart = keystart + len(ids)

	output = struct.pack("<7I",
					0x950412de,        # magic
					0,                 # format revision
					n,                 # number of entries
					7 * 4,             # offset of key table
					7 * 4 + 8 * n,     # offset of value table
					0, 0)              # size/offset of the (absent) hash table

	for length, offset in koffsets:
		output += struct.pack("<2I", length, offset + keystart)
	for length, offset in voffsets:
		output += struct.pack("<2I", length, offset + valuestart)

	return output + ids + strs


#===============================================================================
# payload collection
#===============================================================================

def read_plugin_version():
	fd = io.open(os.path.join(SRC_DIR, "__common__.py"), "r", encoding="utf-8")
	try:
		content = fd.read()
	finally:
		fd.close()
	match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.M)
	if not match:
		raise RuntimeError("could not find version in src/__common__.py")
	return match.group(1)


def iter_data_members():
	"""Yield (arcname, payload_bytes, mode) for every installed file."""

	def read_file(path):
		fd = open(path, "rb")
		try:
			return fd.read()
		finally:
			fd.close()

	# python modules from the src/ root
	for name in sorted(os.listdir(SRC_DIR)):
		if name.endswith(".py"):
			yield ("%s/%s" % (PLUGIN_TARGET, name),
				read_file(os.path.join(SRC_DIR, name)), 0o644)

	# static files from the src/ root
	for name in ROOT_EXTRA_FILES:
		path = os.path.join(SRC_DIR, name)
		if os.path.exists(path):
			yield ("%s/%s" % (PLUGIN_TARGET, name), read_file(path), 0o644)

	# fonts and skins, recursively
	for subdir in ("fonts", "skins"):
		base = os.path.join(SRC_DIR, subdir)
		for root, dirs, files in os.walk(base):
			dirs.sort()
			dirs[:] = [d for d in dirs if d != "__pycache__"]
			for name in sorted(files):
				if name in EXCLUDED_NAMES or name.endswith((".pyc", ".pyo")):
					continue
				path = os.path.join(root, name)
				relative = os.path.relpath(path, SRC_DIR).replace(os.sep, "/")
				yield ("%s/%s" % (PLUGIN_TARGET, relative), read_file(path), 0o644)

	# translations
	for name in sorted(os.listdir(PO_DIR)):
		if not name.endswith(".po"):
			continue
		lang = name[:-3]
		catalog = parse_po(os.path.join(PO_DIR, name))
		if not catalog:
			print("  po: skipping %s (no translated entries)" % name)
			continue
		mo = compile_mo(catalog)
		yield ("%s/locale/%s/LC_MESSAGES/DreamPlex.mo" % (PLUGIN_TARGET, lang), mo, 0o644)


#===============================================================================
# archive writers
#===============================================================================

def build_tar_gz(members, mtime):
	"""members: iterable of (arcname, payload_bytes, mode). Adds parent
	directory entries the way opkg expects."""
	buffer = io.BytesIO()
	tar = tarfile.open(fileobj=buffer, mode="w:gz", format=tarfile.GNU_FORMAT)

	seenDirs = set()

	def add_parents(arcname):
		parts = arcname.split("/")[:-1]
		path = ""
		for part in parts:
			path = path + part + "/" if path else part + "/"
			if path in seenDirs:
				continue
			seenDirs.add(path)
			info = tarfile.TarInfo("./" + path.rstrip("/"))
			info.type = tarfile.DIRTYPE
			info.mode = 0o755
			info.mtime = mtime
			info.uname = "root"
			info.gname = "root"
			tar.addfile(info)

	for arcname, payload, mode in members:
		add_parents(arcname)
		info = tarfile.TarInfo("./" + arcname)
		info.size = len(payload)
		info.mode = mode
		info.mtime = mtime
		info.uname = "root"
		info.gname = "root"
		tar.addfile(info, io.BytesIO(payload))

	tar.close()
	return buffer.getvalue()


def build_control_members(version):
	fd = io.open(os.path.join(CONTROL_DIR, "control"), "r", encoding="utf-8")
	try:
		control = fd.read()
	finally:
		fd.close()

	control = re.sub(r"(?m)^Version:.*$", "Version: " + version, control)
	yield ("control", control.encode("utf-8"), 0o644)

	for script in ("preinst", "postinst", "prerm", "postrm"):
		path = os.path.join(CONTROL_DIR, script)
		if os.path.exists(path):
			fd = open(path, "rb")
			try:
				payload = fd.read().replace(b"\r\n", b"\n")
			finally:
				fd.close()
			yield (script, payload, 0o755)


def main(argv=None):
	parser = argparse.ArgumentParser(description="build the DreamPlex ipk")
	parser.add_argument("--outdir", default=os.path.join(REPO_ROOT, "dist"))
	parser.add_argument("--version-suffix", default="+pms" + time.strftime("%Y%m%d"),
					help="appended to the plugin version (default: +pmsYYYYMMDD)")
	args = parser.parse_args(argv)

	version = read_plugin_version() + args.version_suffix
	mtime = int(time.time())

	print("building version %s" % version)

	dataMembers = list(iter_data_members())
	data = build_tar_gz(dataMembers, mtime)
	control = build_tar_gz(build_control_members(version), mtime)

	outer = [
		("debian-binary", b"2.0\n", 0o644),
		("control.tar.gz", control, 0o644),
		("data.tar.gz", data, 0o644),
	]

	if not os.path.isdir(args.outdir):
		os.makedirs(args.outdir)

	ipkName = "enigma2-plugin-extensions-dreamplex_%s_all.ipk" % version
	ipkPath = os.path.join(args.outdir, ipkName)

	payload = build_tar_gz(outer, mtime)
	fd = open(ipkPath, "wb")
	try:
		fd.write(payload)
	finally:
		fd.close()

	moCount = len([m for m in dataMembers if m[0].endswith(".mo")])
	print("  %d files (%d translation catalogs)" % (len(dataMembers), moCount))
	print("  %s (%.1f KiB)" % (ipkPath, len(payload) / 1024.0))
	print("install with:  opkg install /tmp/%s" % ipkName)
	return 0


if __name__ == "__main__":
	sys.exit(main())
