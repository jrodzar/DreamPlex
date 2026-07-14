# -*- coding: utf-8 -*-
"""Robustness tests: manual access token precedence, HTTP redirect
following, container pagination and modern-PMS attribute guards."""

import unittest

try:
	from tests import helpers, plexmock
except ImportError:  # direct invocation from the tests directory
	import helpers
	import plexmock

helpers.setup_environment()


class RobustnessTestCase(unittest.TestCase):
	def setUp(self):
		self.mock = plexmock.MockPMS().start()
		self.addCleanup(self.mock.stop)

	def newPlex(self, **kwargs):
		return helpers.make_plex_instance(mock=self.mock, **kwargs)

	def url(self, path):
		return "http://%s%s" % (self.mock.address, path)


class TestRedirects(RobustnessTestCase):
	def setUp(self):
		RobustnessTestCase.setUp(self)
		self.mock.add_xml("/library/sections", helpers.fixture("sections.xml"))

	def test_absolute_redirect_is_followed(self):
		self.mock.add_redirect("/old/sections", self.url("/library/sections"), status=302)
		plex = self.newPlex()

		body = plex.doRequest(self.url("/old/sections"))
		self.assertTrue(body)
		self.assertIn(b"MediaContainer", body)
		self.assertEqual([r["path"] for r in self.mock.requests],
						["/old/sections", "/library/sections"])

	def test_relative_redirect_is_followed(self):
		self.mock.add_redirect("/old/relative", "/library/sections", status=301)
		plex = self.newPlex()

		tree = plex.getXmlTreeFromUrl(self.url("/old/relative"))
		self.assertEqual(tree.tag, "MediaContainer")
		self.assertEqual(len(tree.findall("Directory")), 3)

	def test_redirect_chain_up_to_three_hops(self):
		self.mock.add_redirect("/hop1", "/hop2", status=302)
		self.mock.add_redirect("/hop2", "/hop3", status=307)
		self.mock.add_redirect("/hop3", "/library/sections", status=308)
		plex = self.newPlex()

		body = plex.doRequest(self.url("/hop1"))
		self.assertTrue(body)
		self.assertIn(b"MediaContainer", body)

	def test_redirect_loop_gives_up(self):
		self.mock.add_redirect("/loop", "/loop", status=302)
		plex = self.newPlex()

		result = plex.doRequest(self.url("/loop"))
		self.assertFalse(result)
		self.assertIn("redirect", plex.lastError.lower())

	def test_303_switches_to_get(self):
		self.mock.add_redirect("/see/other", "/library/sections", status=303)
		plex = self.newPlex()

		body = plex.doRequest(self.url("/see/other"), myType="PUT")
		self.assertTrue(body)
		methods = [(r["method"], r["path"]) for r in self.mock.requests]
		self.assertEqual(methods, [("PUT", "/see/other"), ("GET", "/library/sections")])


class TestPagination(RobustnessTestCase):
	def pagedItems(self, count):
		return ['<Video ratingKey="%d" key="/library/metadata/%d" type="movie" title="Movie %d"/>'
				% (i, i, i) for i in range(count)]

	def test_pages_are_merged(self):
		self.mock.add_paged("/library/sections/1/all", self.pagedItems(5),
						attrs={"title2": "All Movies"})
		plex = self.newPlex()

		tree = plex.getXmlTreeFromUrlPaged(self.url("/library/sections/1/all"), pageSize=2)

		videos = tree.findall("Video")
		self.assertEqual([v.get("title") for v in videos],
						["Movie 0", "Movie 1", "Movie 2", "Movie 3", "Movie 4"])
		self.assertEqual(tree.get("size"), "5")

		starts = [r["headers"].get("x-plex-container-start")
				for r in self.mock.requests_for("/library/sections/1/all")]
		self.assertEqual(starts, ["0", "2", "4"])

	def test_unpaged_server_needs_single_request(self):
		# a plain xml route has no totalSize -> the merger must stop after one page
		self.mock.add_xml("/library/sections/1/all", helpers.fixture("movies_all.xml"))
		plex = self.newPlex()

		tree = plex.getXmlTreeFromUrlPaged(self.url("/library/sections/1/all"))

		self.assertEqual(len(tree.findall("Video")), 2)
		self.assertEqual(len(self.mock.requests_for("/library/sections/1/all")), 1)

	def test_media_parser_reads_all_pages(self):
		self.mock.add_paged("/library/sections/1/all", self.pagedItems(450),
						attrs={"title2": "All Movies"})
		plex = self.newPlex()

		fullList, mediaContainer = plex.getMoviesFromSection(self.url("/library/sections/1/all"))

		self.assertEqual(len(fullList), 450)
		self.assertEqual(len(self.mock.requests_for("/library/sections/1/all")), 3)  # 200+200+50
		self.assertEqual(mediaContainer["title2"], "All Movies")


class TestManualAccessToken(RobustnessTestCase):
	def setUp(self):
		RobustnessTestCase.setUp(self)
		self.mock.add_xml("/library/sections", helpers.fixture("sections.xml"))

	def lastTokenHeader(self):
		return self.mock.requests_for("/library/sections")[-1]["headers"].get("x-plex-token")

	def test_manual_token_wins_over_local_auth(self):
		plex = self.newPlex(accessToken="MANUAL-TOKEN", localAuth=True,
						myplexToken="PLEXTV-TOKEN", myplexLocalToken="LOCAL-TOKEN")
		plex.doRequest(self.url("/library/sections"))

		self.assertEqual(self.lastTokenHeader(), "MANUAL-TOKEN")
		self.assertEqual(plex.get_rawTokenForServer(self.mock.address), "MANUAL-TOKEN")

	def test_manual_token_works_without_local_auth(self):
		plex = self.newPlex(accessToken="MANUAL-TOKEN")
		plex.doRequest(self.url("/library/sections"))

		self.assertEqual(self.lastTokenHeader(), "MANUAL-TOKEN")

	def test_local_auth_still_works_without_manual_token(self):
		plex = self.newPlex(localAuth=True, myplexToken="PLEXTV-TOKEN",
						myplexLocalToken="LOCAL-TOKEN")
		plex.doRequest(self.url("/library/sections"))

		self.assertEqual(self.lastTokenHeader(), "LOCAL-TOKEN")

	def test_old_saved_config_without_token_field(self):
		# configs saved by older plugin versions have no accessToken element
		helpers.get_config()  # ensure the package is imported
		serverConfig = helpers.make_server_config(
			host=self.mock.host, port=self.mock.port,
			localAuth=True, myplexToken="PLEXTV-TOKEN", myplexLocalToken="LOCAL-TOKEN")
		delattr(serverConfig, "accessToken")

		from src.DP_PlexLibrary import PlexLibrary
		plex = PlexLibrary(session=None, serverConfig=serverConfig)
		plex.doRequest(self.url("/library/sections"))

		self.assertEqual(self.lastTokenHeader(), "LOCAL-TOKEN")


class TestModernContainerGuards(RobustnessTestCase):
	def test_shows_without_title2_do_not_crash(self):
		self.mock.add_xml("/library/sections/2/recentlyAdded",
						helpers.fixture("shows_no_title2.xml"))
		plex = self.newPlex()

		fullList, mediaContainer = plex.getShowsFromSection(
			self.url("/library/sections/2/recentlyAdded"))

		self.assertEqual(len(fullList), 1)
		self.assertEqual(fullList[0][0], "Alpha Show")
		self.assertNotIn("title2", mediaContainer)


if __name__ == "__main__":
	unittest.main()
