# -*- coding: utf-8 -*-
"""HDR in the "Select media to play" dialog.

A box without HDR cannot show an HDR version right: a transcode that keeps
its BT.2020/HLG signalling comes out black (measured with Emby on a Zgemma
H8.2H by the DreamFin fork; whether Plex tone-maps depends on the server).
So every version now carries its HDR kind, the dialog names it, and on a box
without HDR the SDR versions come first - the dialog opens on the first
entry. The version still travels by its own mediaIndex ([7]), never by its
place in the list.

boxSupportsHdr() and the ninth field of buildMediaChoiceName() are shared
with the DreamFin fork (bb3e391) and ported as they are, with their tests.
Reading the kind is Plex's own: the video stream's colorTrc and DOVIPresent.
"""

import os
import shutil
import tempfile
import unittest

try:
	from tests import helpers, plexmock
except ImportError:  # direct invocation from the tests directory
	import helpers
	import plexmock

helpers.setup_environment()

from src.__common__ import boxSupportsHdr, buildMediaChoiceName  # noqa: E402
import src.DP_PlexLibrary as plexlibrary  # noqa: E402


class TestBoxSupportsHdr(unittest.TestCase):
	"""The same files OpenATV 7.0 and 8.0 look at (Components/AVSwitch)."""

	def setUp(self):
		self.root = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, self.root)

	def touch(self, path, content=""):
		full = self.root + path
		if not os.path.isdir(os.path.dirname(full)):
			os.makedirs(os.path.dirname(full))
		with open(full, "w") as handle:
			handle.write(content)

	def test_a_box_with_none_of_them_has_no_hdr(self):
		self.assertFalse(boxSupportsHdr(self.root))

	def test_broadcom(self):
		self.touch("/proc/stb/hdmi/hlg_support_choices", "auto yes no")
		self.assertTrue(boxSupportsHdr(self.root))

	def test_amlogic(self):
		self.touch("/sys/class/amhdmitx/amhdmitx0/config")
		self.assertTrue(boxSupportsHdr(self.root))

	def test_hisilicon_offering_hdr(self):
		self.touch("/proc/stb/video/hdmi_hdrtype", "auto")
		self.touch("/proc/stb/video/hdmi_hdrtype_choices", "auto sdr hdr10 hlg")
		self.assertTrue(boxSupportsHdr(self.root))

	def test_hisilicon_offering_only_sdr(self):
		self.touch("/proc/stb/video/hdmi_hdrtype", "auto")
		self.touch("/proc/stb/video/hdmi_hdrtype_choices", "auto sdr")
		self.assertFalse(boxSupportsHdr(self.root))

	def test_hisilicon_without_its_choices(self):
		self.touch("/proc/stb/video/hdmi_hdrtype", "auto")
		self.assertTrue(boxSupportsHdr(self.root))

	def test_a_1080p_box_whose_driver_lists_hdr_types_has_no_hdr(self):
		"""The Zgemma H8.2H as read on the box (hi3716mv430, 2026-10-05)."""
		self.touch("/proc/stb/video/hdmi_hdrtype", "auto")
		self.touch("/proc/stb/video/hdmi_hdrtype_choices", "none auto autofirstframe dolby hdr10 hlg")
		self.touch("/proc/stb/video/videomode_choices",
				"pal ntsc 720p 720p50 1080i 1080i50 1080p24 1080p25 1080p30 1080p50 1080p 576i 576p 480i 480p")
		self.assertFalse(boxSupportsHdr(self.root))

	def test_a_4k_box_with_hdr_types(self):
		self.touch("/proc/stb/video/hdmi_hdrtype", "auto")
		self.touch("/proc/stb/video/hdmi_hdrtype_choices", "auto sdr hdr10 hlg")
		self.touch("/proc/stb/video/videomode_choices", "720p 1080i 1080p 2160p24 2160p25 2160p50 2160p")
		self.assertTrue(boxSupportsHdr(self.root))


class TestTheDialogNamesTheKind(unittest.TestCase):
	def test_the_hdr_kind_goes_into_the_prefix(self):
		items = ("/library/parts/3301/1/file.mkv", "/data/movies/Movie.2160p.mkv",
				"mkv", "4710000000", "6792", "4K", "hevc", 0, "HLG")

		self.assertEqual(buildMediaChoiceName(items),
				"[4K / hevc / HLG / 4.39 GB]  Movie.2160p.mkv")

	def test_an_sdr_version_says_nothing_about_it(self):
		items = ("/library/parts/3302/1/file.mkv", "/data/movies/Movie.1080p.mkv",
				"mkv", "1073741824", "6792", "1080", "hevc", 1, "")

		self.assertEqual(buildMediaChoiceName(items),
				"[1080 / hevc / 1.0 GB]  Movie.1080p.mkv")

	def test_eight_fields_still_work(self):
		items = ("/library/parts/3302/1/file.mkv", "/data/movies/Movie.1080p.mkv",
				"mkv", "1073741824", "6792", "1080", "hevc", 1)

		self.assertEqual(buildMediaChoiceName(items),
				"[1080 / hevc / 1.0 GB]  Movie.1080p.mkv")


class TestPlexVersions(unittest.TestCase):
	"""Four versions on the mock PMS: 4K HLG, 1080p SDR, 4K Dolby Vision and
	4K HDR10, in that order (mediaIndex 0-3)."""

	def setUp(self):
		self.mock = plexmock.MockPMS().start()
		self.addCleanup(self.mock.stop)
		self.mock.add_xml("/library/metadata/1005", helpers.fixture("metadata_hdr_versions.xml"))
		self.addCleanup(setattr, plexlibrary, "boxSupportsHdr", plexlibrary.boxSupportsHdr)

	def options(self, ratingKey="1005", hdr=None, loadExtraData=False):
		if hdr is None:
			def unexpected():
				raise AssertionError("boxSupportsHdr() asked although nothing needs reordering")
			plexlibrary.boxSupportsHdr = unexpected
		else:
			plexlibrary.boxSupportsHdr = lambda: hdr
		plex = helpers.make_plex_instance(mock=self.mock)
		count, options, server = plex.getMediaOptionsToPlay(
			ratingKey, "http://%s/library/sections/1/all" % self.mock.address, False,
			myType="Video", loadExtraData=loadExtraData)
		return options

	def test_each_version_carries_its_kind(self):
		options = self.options(hdr=True)

		self.assertEqual(dict((o[7], o[8]) for o in options), {0: "HLG", 1: "", 2: "DV", 3: "HDR10"})

	def test_a_box_with_hdr_keeps_the_servers_order(self):
		self.assertEqual([o[7] for o in self.options(hdr=True)], [0, 1, 2, 3])

	def test_a_box_without_hdr_gets_sdr_first(self):
		# stable: the HDR versions keep their relative order behind it
		self.assertEqual([o[7] for o in self.options(hdr=False)], [1, 0, 2, 3])

	def test_the_chosen_version_still_travels_by_its_own_index(self):
		options = self.options(hdr=False)

		# what DP_Player.setSelectedMedia() does with the dialog's first entry
		chosen = options[0]
		self.assertTrue(chosen[0].endswith("file-sdr.mkv"))
		self.assertEqual(chosen[7], 1)

	def test_the_dialog_label_names_the_kind(self):
		labels = [buildMediaChoiceName(o) for o in self.options(hdr=True)]

		self.assertTrue(labels[0].startswith("[4k / hevc / HLG / "), labels[0])
		self.assertTrue(labels[1].startswith("[1080 / h264 / "), labels[1])
		self.assertTrue(labels[2].startswith("[4k / hevc / DV / "), labels[2])

	def test_a_list_that_does_not_mix_ranges_never_asks_the_box(self):
		# both versions SDR as far as Plex says (no colorTrc on either)
		self.mock.add_xml("/library/metadata/1002", helpers.fixture("metadata_multiversion.xml"))

		options = self.options(ratingKey="1002")

		self.assertEqual([o[7] for o in options], [0, 1])

	def test_extras_are_left_alone(self):
		self.mock.add_xml("/library/metadata/1003", helpers.fixture("metadata_trailer_extras.xml"))

		options = self.options(ratingKey="1003", loadExtraData=True)

		self.assertEqual(len(options), 1)
		self.assertEqual(len(options[0]), 6)


if __name__ == "__main__":
	unittest.main()
