# -*- coding: utf-8 -*-
"""Bug 1 regression tests: modern PMS answers /library/sections/<id>
without the legacy secondary navigation, so the section filter menu must
be synthesized client-side and filter drill-ins must use fastKey."""

import unittest

try:
	from tests import helpers, plexmock
except ImportError:  # direct invocation from the tests directory
	import helpers
	import plexmock

helpers.setup_environment()

from src.__plugin__ import Plugin  # noqa: E402


class SectionFilterTestCase(unittest.TestCase):
	def setUp(self):
		self.mock = plexmock.MockPMS().start()
		self.addCleanup(self.mock.stop)
		self.mock.add_xml("/library/sections", helpers.fixture("sections.xml"))

	def newPlex(self, **kwargs):
		return helpers.make_plex_instance(mock=self.mock, **kwargs)

	def findEntry(self, fullList, title):
		for entry in fullList:
			if entry[0] == title:
				return entry
		self.fail("entry %r not found in %r" % (title, [e[0] for e in fullList]))

	def sectionEntryData(self, plex, sectionTitle):
		return self.findEntry(plex.getAllSections(), sectionTitle)[3]


class TestSynthesizedMovieMenu(SectionFilterTestCase):
	def setUp(self):
		SectionFilterTestCase.setUp(self)
		self.mock.add_xml("/library/sections/1", helpers.fixture("section_root_modern.xml"))

	def test_section_roots_are_marked(self):
		plex = self.newPlex()
		entryData = self.sectionEntryData(plex, "Movies")
		self.assertTrue(entryData.get("isSectionRoot"))

	def test_movie_menu_is_synthesized(self):
		plex = self.newPlex()
		entryData = self.sectionEntryData(plex, "Movies")
		root = entryData["contentUrl"]

		menu = plex.getSectionFilter(entryData)

		self.assertEqual([e[0] for e in menu],
						["All Movies", "Unwatched", "Recently Added",
						"Recently Released", "On Deck", "By Genre",
						"By Year", "By Decade", "Search..."])
		self.assertIsNone(plex.lastError)

		allMovies = self.findEntry(menu, "All Movies")
		self.assertEqual(allMovies[2], "movieEntry")
		self.assertNotEqual(allMovies[1], Plugin.MENU_FILTER)
		self.assertEqual(allMovies[3]["contentUrl"], root + "/all")
		self.assertEqual(allMovies[3]["key"], "all")
		self.assertEqual(allMovies[3]["type"], "movie")
		self.assertFalse(allMovies[3]["hasSecondaryTag"])
		self.assertTrue(allMovies[3]["synthesized"])

		unwatched = self.findEntry(menu, "Unwatched")
		self.assertEqual(unwatched[3]["contentUrl"], root + "/all?unwatched=1")

		genre = self.findEntry(menu, "By Genre")
		self.assertEqual(genre[1], Plugin.MENU_FILTER)
		self.assertEqual(genre[2], "showFilter")
		self.assertTrue(genre[3]["hasSecondaryTag"])
		self.assertEqual(genre[3]["contentUrl"], root + "/genre")

		search = self.findEntry(menu, "Search...")
		self.assertTrue(search[3]["hasPromptTag"])
		self.assertEqual(search[3]["contentUrl"], root + "/search?type=1")

	def test_fastkey_is_used_for_filter_values(self):
		self.mock.add_xml("/library/sections/1/genre", helpers.fixture("genres_modern.xml"))
		plex = self.newPlex()
		entryData = self.sectionEntryData(plex, "Movies")

		menu = plex.getSectionFilter(entryData)
		genreMenu = self.findEntry(menu, "By Genre")

		values = plex.getSectionFilter(genreMenu[3])
		self.assertEqual(len(values), 3)

		action = self.findEntry(values, "Action")
		self.assertEqual(action[2], "movieEntry")
		self.assertEqual(action[3]["type"], "movie")
		# fastKey, not the legacy contentUrl + "/" + key drill-in
		self.assertEqual(action[3]["contentUrl"],
						"http://%s/library/sections/1/all?genre=101" % self.mock.address)


class TestSynthesizedShowMenu(SectionFilterTestCase):
	def setUp(self):
		SectionFilterTestCase.setUp(self)
		self.mock.add_xml("/library/sections/2", helpers.fixture("section_root_modern.xml"))

	def test_show_menu_is_synthesized(self):
		plex = self.newPlex()
		entryData = self.sectionEntryData(plex, "TV Shows")
		root = entryData["contentUrl"]

		menu = plex.getSectionFilter(entryData)

		self.assertEqual([e[0] for e in menu],
						["All Shows", "Unwatched", "Recently Added",
						"On Deck", "By Genre", "By Year", "Search..."])

		allShows = self.findEntry(menu, "All Shows")
		self.assertEqual(allShows[2], "showEntry")
		self.assertEqual(allShows[3]["contentUrl"], root + "/all")

		# DP_LibShows switches to its direct Video+Directory parser for
		# exactly these key values - the keys are a contract
		recentlyAdded = self.findEntry(menu, "Recently Added")
		self.assertEqual(recentlyAdded[3]["key"], "recentlyAdded")
		self.assertNotIn("nextViewMode", recentlyAdded[3])

		onDeck = self.findEntry(menu, "On Deck")
		self.assertEqual(onDeck[3]["key"], "onDeck")

		search = self.findEntry(menu, "Search...")
		self.assertEqual(search[3]["contentUrl"], root + "/search?type=2")


class TestSynthesizedMusicMenu(SectionFilterTestCase):
	def setUp(self):
		SectionFilterTestCase.setUp(self)
		self.mock.add_xml("/library/sections/3", helpers.fixture("section_root_modern.xml"))

	def test_music_menu_is_synthesized(self):
		plex = self.newPlex()
		entryData = self.sectionEntryData(plex, "Music")
		root = entryData["contentUrl"]

		menu = plex.getSectionFilter(entryData)

		self.assertEqual([e[0] for e in menu],
						["All Artists", "Recently Added", "By Genre", "Search..."])

		allArtists = self.findEntry(menu, "All Artists")
		self.assertEqual(allArtists[2], "musicEntry")
		self.assertEqual(allArtists[3]["contentUrl"], root + "/all")
		self.assertNotIn("nextViewMode", allArtists[3])

		# recently added music lists albums -> must go to the album parser
		recentlyAdded = self.findEntry(menu, "Recently Added")
		self.assertEqual(recentlyAdded[3]["nextViewMode"], "ShowAlbums")
		self.assertEqual(recentlyAdded[3]["currentViewMode"], "ShowAlbums")

		search = self.findEntry(menu, "Search...")
		self.assertEqual(search[3]["contentUrl"], root + "/search?type=8")


class TestNoSynthesisCases(SectionFilterTestCase):
	def test_legacy_server_menu_is_passed_through(self):
		self.mock.add_xml("/library/sections/1", helpers.fixture("section_root_legacy.xml"))
		plex = self.newPlex()
		entryData = self.sectionEntryData(plex, "Movies")

		menu = plex.getSectionFilter(entryData)
		self.assertEqual(len(menu), 6)
		for entry in menu:
			self.assertNotIn("synthesized", entry[3])

	def test_empty_answer_without_root_marker_sets_error(self):
		self.mock.add_xml("/library/sections/1", helpers.fixture("section_root_modern.xml"))
		plex = self.newPlex()
		entryData = {
			"contentUrl": "http://%s/library/sections/1" % self.mock.address,
			"type": "movie",
		}

		menu = plex.getSectionFilter(entryData)
		self.assertEqual(menu, [])
		self.assertTrue(plex.lastError)

	def test_unparseable_answer_is_not_synthesized(self):
		# no route registered -> 404 -> fake xml tree, not a MediaContainer
		plex = self.newPlex()
		entryData = {
			"contentUrl": "http://%s/library/sections/9" % self.mock.address,
			"type": "movie",
			"isSectionRoot": True,
		}

		menu = plex.getSectionFilter(entryData)
		self.assertEqual(menu, [])
		self.assertTrue(plex.lastError)


if __name__ == "__main__":
	unittest.main()
