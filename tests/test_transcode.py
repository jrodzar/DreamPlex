# -*- coding: utf-8 -*-
"""Bug 2 regression tests: the transcode URL builder must work on
Python 3 (bytes-safe m3u8 parsing), drop the 2010 X-Plex-Access
signature, carry the X-Plex-Token in playback URLs and never crash on
a missing token."""

import unittest

try:
	from tests import helpers, plexmock
except ImportError:  # direct invocation from the tests directory
	import helpers
	import plexmock

helpers.setup_environment()


class PlaybackTestCase(unittest.TestCase):
	def setUp(self):
		self.mock = plexmock.MockPMS().start()
		self.addCleanup(self.mock.stop)
		self.mock.add_xml("/", helpers.fixture("server_root.xml"))
		self.mock.add_xml("/library/metadata/1001", helpers.fixture("metadata_video.xml"))

	def newPlex(self, **kwargs):
		kwargs.setdefault("localAuth", True)
		kwargs.setdefault("myplexToken", "PLEXTV-TOKEN")
		kwargs.setdefault("myplexLocalToken", "LOCAL-TOKEN")
		return helpers.make_plex_instance(mock=self.mock, **kwargs)

	def playFirstPart(self, plex):
		"""Mimic DP_Player: options -> mediaType -> playLibraryMedia."""
		vids = "http://%s/library/sections/1/all" % self.mock.address
		count, options, server = plex.getMediaOptionsToPlay("1001", vids, False, myType="Video")
		self.assertEqual(count, 1)
		mediaFileUrl = plex.mediaType({"key": options[0][0], "file": options[0][1]}, server)
		return plex.playLibraryMedia("1001", mediaFileUrl)


class TestAppendTokenToUrl(PlaybackTestCase):
	def test_token_is_appended_with_correct_separator(self):
		plex = self.newPlex()
		server = self.mock.address
		base = "http://%s/library/parts/3001/file.mkv" % server

		self.assertEqual(plex.appendTokenToUrl(base, server),
						base + "?X-Plex-Token=LOCAL-TOKEN")
		self.assertEqual(plex.appendTokenToUrl(base + "?a=1", server),
						base + "?a=1&X-Plex-Token=LOCAL-TOKEN")

	def test_append_is_idempotent(self):
		plex = self.newPlex()
		server = self.mock.address
		url = "http://%s/video?X-Plex-Token=LOCAL-TOKEN" % server
		self.assertEqual(plex.appendTokenToUrl(url, server), url)

	def test_without_token_url_is_unchanged(self):
		plex = self.newPlex(localAuth=False, myplexToken="", myplexLocalToken="")
		url = "http://%s/library/parts/3001/file.mkv" % self.mock.address
		self.assertEqual(plex.appendTokenToUrl(url, self.mock.address), url)

	def test_unknown_server_returns_url_unchanged(self):
		plex = self.newPlex()
		url = "http://192.0.2.1:32400/library/parts/1/file.mkv"
		self.assertEqual(plex.appendTokenToUrl(url, "192.0.2.1:32400"), url)


class TestStreamedPlayback(PlaybackTestCase):
	def test_raw_stream_url_carries_token(self):
		plex = self.newPlex(playbackType="0")
		playerData = self.playFirstPart(plex)

		self.assertEqual(playerData["playUrl"],
						"http://%s/library/parts/3001/1700000000/file.mkv?X-Plex-Token=LOCAL-TOKEN"
						% self.mock.address)
		self.assertEqual(playerData["resumeStamp"], 60000)

	def test_raw_stream_without_token_does_not_crash(self):
		plex = self.newPlex(playbackType="0", localAuth=False,
						myplexToken="", myplexLocalToken="")
		playerData = self.playFirstPart(plex)

		# upstream crashed here with TypeError: url + None
		self.assertEqual(playerData["playUrl"],
						"http://%s/library/parts/3001/1700000000/file.mkv" % self.mock.address)


class TestUniversalTranscoder(PlaybackTestCase):
	M3U8_PATH = "/video/:/transcode/universal/start.m3u8"

	def test_transcode_url_is_py3_safe_and_tokenized(self):
		self.mock.add_raw(self.M3U8_PATH, "application/vnd.apple.mpegurl",
						helpers.fixture("start.m3u8"))
		plex = self.newPlex(playbackType="1")
		playerData = self.playFirstPart(plex)
		playUrl = playerData["playUrl"]

		self.assertEqual(playUrl,
						"http://%s/video/:/transcode/universal/"
						"session/f00dcafe-0000-1111-2222-333344445555/base/index.m3u8"
						"?X-Plex-Token=LOCAL-TOKEN" % self.mock.address)
		self.assertNotIn("b'", playUrl)  # the py3 bytes corruption

	def test_prefetch_request_is_authenticated_and_unsigned(self):
		self.mock.add_raw(self.M3U8_PATH, "application/vnd.apple.mpegurl",
						helpers.fixture("start.m3u8"))
		plex = self.newPlex(playbackType="1")
		self.playFirstPart(plex)

		prefetch = self.mock.requests_for(self.M3U8_PATH)[-1]
		headers = prefetch["headers"]
		self.assertEqual(headers.get("x-plex-token"), "LOCAL-TOKEN")
		self.assertEqual(headers.get("x-plex-product"), "DreamPlex")

		# the 2010 signature scheme must be gone
		self.assertNotIn("x-plex-access-code", headers)
		self.assertNotIn("x-plex-access-key", headers)
		self.assertNotIn("x-plex-access-time", headers)

		query = prefetch["query"]
		self.assertEqual(query.get("session"), [plex.g_sessionID])
		self.assertEqual(query.get("protocol"), ["hls"])
		self.assertEqual(query.get("X-Plex-Token"), ["LOCAL-TOKEN"])
		# the universal transcoder needs the library path of the item
		self.assertEqual(query.get("path"),
						["http://127.0.0.1:32400/library/metadata/1001"])

	def test_fallback_to_master_playlist_when_no_media_urls(self):
		self.mock.add_raw(self.M3U8_PATH, "application/vnd.apple.mpegurl",
						helpers.fixture("start_comments_only.m3u8"))
		plex = self.newPlex(playbackType="1")
		playerData = self.playFirstPart(plex)
		playUrl = playerData["playUrl"]

		self.assertTrue(playUrl.startswith(
			"http://%s/video/:/transcode/universal/start.m3u8?" % self.mock.address))
		self.assertIn("session=%s" % plex.g_sessionID, playUrl)
		self.assertIn("&X-Plex-Token=LOCAL-TOKEN", playUrl)

	def test_fallback_when_server_answers_error(self):
		self.mock.add_error(self.M3U8_PATH, 500)
		plex = self.newPlex(playbackType="1")
		playerData = self.playFirstPart(plex)
		playUrl = playerData["playUrl"]

		self.assertTrue(playUrl.startswith(
			"http://%s/video/:/transcode/universal/start.m3u8?" % self.mock.address))
		self.assertIn("&X-Plex-Token=LOCAL-TOKEN", playUrl)


class TestSegmentedTranscoder(PlaybackTestCase):
	M3U8_PATH = "/video/:/transcode/segmented/start.m3u8"

	def test_segmented_branch_is_py3_safe(self):
		self.mock.add_raw(self.M3U8_PATH, "application/vnd.apple.mpegurl",
						helpers.fixture("start.m3u8"))
		plex = self.newPlex(playbackType="1", universalTranscoder=False)
		playerData = self.playFirstPart(plex)
		playUrl = playerData["playUrl"]

		self.assertEqual(playUrl,
						"http://%s/video/:/transcode/segmented/"
						"session/f00dcafe-0000-1111-2222-333344445555/base/index.m3u8"
						"?X-Plex-Token=LOCAL-TOKEN" % self.mock.address)
		self.assertNotIn("b'", playUrl)

		prefetch = self.mock.requests_for(self.M3U8_PATH)[-1]
		self.assertEqual(prefetch["query"].get("ratingKey"), ["1001"])
		self.assertNotIn("x-plex-access-code", prefetch["headers"])


if __name__ == "__main__":
	unittest.main()
