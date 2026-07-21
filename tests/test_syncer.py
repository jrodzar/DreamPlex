# -*- coding: utf-8 -*-
"""Syncer downloads.

The image download used URLopener, which Python 3.14 removed - taking the
whole plugin (and, being Autostart, enigma2) down on OpenATV 8.0. It now uses
urlopen/Request; these tests pin the replacement's behaviour: the bytes must
land in the file and the server token must still travel with the request,
which the old code did via URLopener.addheader().
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

from src.DP_Syncer import BackgroundMediaSyncer


class TestSyncerDownload(unittest.TestCase):
	def setUp(self):
		self.mock = plexmock.MockPMS().start()
		self.addCleanup(self.mock.stop)
		self.tmp = tempfile.mkdtemp(prefix="dreamplex-syncer-")
		self.addCleanup(shutil.rmtree, self.tmp, True)

	def newSyncer(self, headers):
		# BackgroundMediaSyncer is a Thread whose __init__ wires the whole
		# plugin up; we only exercise the download helper
		syncer = BackgroundMediaSyncer.__new__(BackgroundMediaSyncer)
		syncer.downloadHeaders = headers
		return syncer

	def test_downloads_the_bytes_to_the_file(self):
		self.mock.add_raw("/photo/poster.jpg", "image/jpeg", b"BINARY-POSTER-DATA")
		syncer = self.newSyncer({})
		target = os.path.join(self.tmp, "poster.jpg")

		syncer.retrieveToFile("http://%s/photo/poster.jpg" % self.mock.address, target)

		with open(target, "rb") as handle:
			self.assertEqual(handle.read(), b"BINARY-POSTER-DATA")

	def test_sends_the_server_token(self):
		self.mock.add_raw("/photo/poster.jpg", "image/jpeg", b"x")
		syncer = self.newSyncer({"X-Plex-Token": "tok-123"})

		syncer.retrieveToFile("http://%s/photo/poster.jpg" % self.mock.address,
				os.path.join(self.tmp, "poster.jpg"))

		record = self.mock.requests[-1]
		self.assertEqual(record["headers"].get("x-plex-token"), "tok-123")

	def test_works_without_headers(self):
		# downloadHeaders is None until initDownloadHeaders() ran
		self.mock.add_raw("/photo/poster.jpg", "image/jpeg", b"y")
		syncer = self.newSyncer(None)

		syncer.retrieveToFile("http://%s/photo/poster.jpg" % self.mock.address,
				os.path.join(self.tmp, "poster.jpg"))

		record = self.mock.requests[-1]
		self.assertIsNone(record["headers"].get("x-plex-token"))


if __name__ == "__main__":
	unittest.main()
