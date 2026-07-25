# -*- coding: utf-8 -*-
"""Waking a server must not freeze the GUI.

sleepNow() is reached from a MessageBox callback, so it runs on the enigma2
main loop. It used to hold a time.sleep(wol_delay) - 60 seconds by default
and up to 180 - which blocks everything: no key is processed, and a block
that long is what the image's hang detector kills enigma2 for.

Checked on the source: DP_MainMenu pulls in enigma2, so it cannot be
imported offline.

Found while chasing the DreamFin report about the blue button; the scale
(default 60, not 10) came back from them.
"""

import ast
import io
import os
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
MAINMENU = os.path.join(SRC, "DP_MainMenu.py")
INIT = os.path.join(SRC, "__init__.py")


def readSource(path):
	handle = io.open(path, "rb")
	try:
		return handle.read()
	finally:
		handle.close()


def findFunction(name):
	tree = ast.parse(readSource(MAINMENU), filename=MAINMENU)
	for node in ast.walk(tree):
		if isinstance(node, ast.FunctionDef) and node.name == name:
			return node

	raise AssertionError("%s() not found in DP_MainMenu.py" % name)


def calledNames(node):
	names = set()
	for child in ast.walk(node):
		if isinstance(child, ast.Call):
			names.add(getattr(child.func, "id", None) or getattr(child.func, "attr", None))

	return names


class TestWakeOnLanDoesNotBlock(unittest.TestCase):
	def test_no_sleep_while_waiting_for_the_server(self):
		sleepNow = findFunction("sleepNow")

		self.assertNotIn("sleep", calledNames(sleepNow),
				"sleepNow() runs on the main loop: sleeping here freezes the "
				"GUI for the whole wol_delay")

	def test_waits_with_a_timer_instead(self):
		sleepNow = findFunction("sleepNow")

		self.assertIn("eTimer", calledNames(sleepNow),
				"the wait has to be handed to a timer")

	def test_the_timer_is_imported(self):
		# DP_MainMenu had no `from enigma` import at all, so using eTimer
		# without adding it would only blow up on a real Wake on Lan - a
		# path almost nobody exercises (caught by DreamFin)
		source = readSource(MAINMENU).decode("utf-8")

		self.assertIn("from enigma import eTimer", source)

	def test_the_server_is_still_checked_afterwards(self):
		# the point of the wait is to look at the server again
		names = calledNames(findFunction("sleepNow"))
		names |= calledNames(findFunction("wolDelayElapsed"))

		self.assertIn("checkServerState", names)

	def test_a_live_timer_is_never_replaced(self):
		sleepNow = findFunction("sleepNow")

		guarded = False
		for node in ast.walk(sleepNow):
			if not isinstance(node, ast.If):
				continue
			condition = ast.dump(node.test)
			if "wolTimer" not in condition or "None" not in condition:
				continue
			if any(isinstance(c, ast.Call) and getattr(c.func, "id", None) == "eTimer"
					for c in ast.walk(node)):
				guarded = True

		self.assertTrue(guarded,
				"building a new eTimer over a live one drops the last "
				"reference to it while its callback may be on the stack")


class TestTheDelayIsAsLongAsDocumented(unittest.TestCase):
	"""Guards the reasoning above: this is a minute, not a moment."""

	def test_default_delay_is_the_one_we_reasoned_about(self):
		source = readSource(INIT).decode("utf-8")

		self.assertIn("wol_delay = ConfigInteger(default=60, limits=(1, 180))", source,
				"if this default changes, revisit how bad a blocking wait is")


if __name__ == "__main__":
	unittest.main()
