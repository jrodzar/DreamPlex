# -*- coding: utf-8 -*-
"""Busy-spinner helper (DPH_ScreenHelper.startBusy/stopBusy/_busyTick).

Now that network I/O runs off the enigma2 main loop the GUI stays alive, so
the user needs a "working..." hint. The spinner is a MultiPixmap rotated by
an eTimer; it must also degrade to a no-op when the active skin does not ship
the widget (external skins), so the text hint stays the universal fallback.
"""

import unittest

try:
	from tests import helpers
except ImportError:  # direct invocation from the tests directory
	import helpers

helpers.setup_environment()

from src.DPH_ScreenHelper import DPH_ScreenHelper


class _FakePixmap(object):
	def __init__(self, has_instance=True):
		self.instance = object() if has_instance else None
		self.shown = False
		self.hidden = False
		self.nums = []

	def show(self):
		self.shown = True
		self.hidden = False

	def hide(self):
		self.hidden = True
		self.shown = False

	def setPixmapNum(self, num):
		self.nums.append(num)


class _Host(DPH_ScreenHelper):
	"""A DPH_ScreenHelper standing in for a Screen: just a widget dict."""
	def __init__(self, widgets):
		self._widgets = widgets

	def __contains__(self, key):
		return key in self._widgets

	def __getitem__(self, key):
		return self._widgets[key]


class TestBusySpinner(unittest.TestCase):
	def test_start_shows_and_arms_timer_from_frame_zero(self):
		w = _FakePixmap()
		host = _Host({"busy": w})

		host.startBusy()

		self.assertTrue(w.shown)
		self.assertEqual(w.nums[0], 0)
		self.assertIsNotNone(host._busyTimer)
		# the tick is wired as the timer callback
		self.assertIn(host._busyTick, host._busyTimer.callback)

	def test_tick_advances_and_wraps_modulo_frames(self):
		w = _FakePixmap()
		host = _Host({"busy": w})
		host.startBusy()

		seen = []
		for _ in range(DPH_ScreenHelper.BUSY_FRAMES + 2):
			host._busyTick()
			seen.append(w.nums[-1])

		# advances 1,2,3,... then wraps back through 0
		self.assertEqual(seen[:3], [1, 2, 3])
		self.assertEqual(seen[DPH_ScreenHelper.BUSY_FRAMES - 1], 0)
		self.assertTrue(all(0 <= n < DPH_ScreenHelper.BUSY_FRAMES for n in w.nums))

	def test_stop_hides_the_widget(self):
		w = _FakePixmap()
		host = _Host({"busy": w})
		host.startBusy()

		host.stopBusy()

		self.assertTrue(w.hidden)
		self.assertFalse(w.shown)

	def test_no_widget_in_skin_is_a_silent_no_op(self):
		host = _Host({})  # external skin: no "busy" widget at all

		# must not raise, and must not invent a timer to fire later
		host.startBusy()
		host._busyTick()
		host.stopBusy()

		self.assertIsNone(host.getBusyWidget())

	def test_widget_without_instance_is_treated_as_absent(self):
		# widget declared in code but not placed by this skin -> instance None
		w = _FakePixmap(has_instance=False)
		host = _Host({"busy": w})

		host.startBusy()

		self.assertIsNone(host.getBusyWidget())
		self.assertEqual(w.nums, [])   # never touched
		self.assertFalse(w.shown)

	def test_stop_without_start_does_not_raise(self):
		host = _Host({"busy": _FakePixmap()})
		host.stopBusy()  # no timer created yet

	def test_caption_is_shown_and_hidden_with_the_spinner(self):
		w = _FakePixmap()
		caption = _FakePixmap()
		host = _Host({"busy": w, "busyText": caption})

		host.startBusy()
		self.assertTrue(caption.shown)

		host.stopBusy()
		self.assertTrue(caption.hidden)

	def test_missing_caption_is_fine(self):
		# spinner but no busyText widget (e.g. an older skin revision)
		w = _FakePixmap()
		host = _Host({"busy": w})

		host.startBusy()   # must not raise
		host.stopBusy()
		self.assertIsNone(host.getBusyTextWidget())


if __name__ == "__main__":
	unittest.main()
