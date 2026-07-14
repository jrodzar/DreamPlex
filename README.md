DreamPlex — fork for modern Plex Media Server
==============================================

Plex client for Enigma2 (OpenATV and friends), forked from
[oe-alliance/DreamPlex](https://github.com/oe-alliance/DreamPlex) to make it
work again with current Plex Media Server releases, on **both**
OpenATV 6.4 (Python 2.7) and OpenATV 6.5+/7.x (Python 3).

What was broken and what this fork fixes
----------------------------------------

**1. "No data in this section!" when opening any library**

With the default setting *Show filter for sections* enabled (and always for
music sections), the plugin asks the server for the legacy secondary
navigation of a section (`GET /library/sections/<id>`) and builds its menu
from the `<Directory>` children (All / Unwatched / By Genre / ...). Modern
PMS releases no longer answer with those children, so every library appeared
empty; only the global "New" / "On Deck" rows kept working because they use a
direct content endpoint.

The fork detects the empty answer and **synthesizes the filter menu on the
client**, with the same entries the server used to send:

* Movies: All, Unwatched, Recently Added, Recently Released, On Deck,
  By Genre, By Year, By Decade, Search
* Shows: All, Unwatched, Recently Added, On Deck, By Genre, By Year, Search
* Music: All Artists, Recently Added, By Genre, Search

Old servers that still send their own menu keep being used unchanged.
Drilling into a filter value (a genre, a year...) now follows the `fastKey`
attribute of the server answer (`/library/sections/<id>/all?genre=<id>`),
because the legacy `<section>/genre/<id>` path no longer exists either.

**2. Transcoding only worked on OpenATV 6.4**

The Python 3 port left `transcode()` iterating the m3u8 master playlist as
*bytes*: the `#` comment check compared an integer with a string (always
true) and the URL formatting injected `b'...'` fragments, so the player
received a corrupt URL on every Python 3 image. The fork decodes the playlist
before parsing (works on py2 and py3), removes the long-dead 2010
`X-Plex-Access-Key/Time/Code` request signature, sends the `X-Plex-Token`
both while prefetching and **inside the final playback URL** (the media
player cannot send headers), and falls back to handing GStreamer the
tokenized `start.m3u8` if no media playlist can be parsed.

**3. Robustness extras**

* New per-server **"Access Token (optional)"** field (IP/DNS connections):
  paste an X-Plex-Token and it wins over any other token source. This lets
  the plugin work against servers that require authentication without going
  through plex.tv on the box.
* Playback URLs for raw streaming also carry the token now, and a missing
  token no longer crashes playback (`url + None`).
* `doRequest()` follows HTTP redirects (301/302/303/307/308, absolute and
  relative `Location`, up to 3 hops).
* Big libraries are fetched **paginated** (`X-Plex-Container-Start/Size`,
  200 items per page) and merged, instead of relying on one giant answer.
* Parser guards for answers of modern servers (missing `title2`, poster
  downloads without a known token, unparseable payloads are logged).

Installation
------------

Build the package (any OS, only Python needed):

    py -3 tools/build_ipk.py        # Windows
    python3 tools/build_ipk.py      # Linux/macOS

Copy the resulting `dist/enigma2-plugin-extensions-dreamplex_*.ipk` to the
receiver and install it there:

    scp dist/enigma2-plugin-extensions-dreamplex_*.ipk root@<box-ip>:/tmp/
    ssh root@<box-ip>
    opkg install /tmp/enigma2-plugin-extensions-dreamplex_*.ipk

Then restart the enigma2 GUI. The package uses the same name as the OpenATV
feed package and a higher version, so it cleanly **upgrades an existing feed
installation** and survives `opkg upgrade` runs (the feed would need to
publish something newer than `2.3.1` to replace it; pin it with
`opkg flag hold enigma2-plugin-extensions-dreamplex` if you want to be sure).

Works on OpenATV 6.4 (Python 2.7) and OpenATV 6.5/7.x (Python 3). The plugin
needs the `six` module, which both image generations ship by default; if it
is ever missing: `opkg install python-six` (6.4) or `opkg install
python3-six` (6.5+).

How to get your X-Plex-Token
----------------------------

Only needed if your server requires authentication for local connections
(Plex settings → Network → *List of IP addresses and networks that are
allowed without auth* is empty) and you connect by IP/DNS without plex.tv:

1. Open Plex Web in a browser, play any item of your server.
2. Click the ⋮ menu of the item → *Get Info* → *View XML*.
3. Look at the address bar of the opened tab: it ends with
   `...&X-Plex-Token=xxxxxxxxxxxxxxxxxxxx`. That value is your token.
4. In DreamPlex: server settings → *Access Token (optional)* → enter it.

(Official article: support.plex.tv → "Finding an authentication token".)

Verification checklist after installing
---------------------------------------

* About screen shows version 2.3.1.
* Movies: All / Unwatched / Recently Added / On Deck list content; By Genre →
  pick a genre → movies of that genre appear; Search finds a known title.
* Shows: All → seasons → episodes; Recently Added lists the latest episodes
  and seasons.
* Music: artists → albums → tracks.
* Global "New" and "On Deck" rows still work.
* Playback *Streamed* plays.
* Playback *Transcoded* plays **and** a transcode session shows up on the
  PMS dashboard (both on a 6.4 and a 7.x box if you have them).
* With server auth hardened (empty no-auth list) and the Access Token field
  filled, all of the above still works.
* Logs if something fails: enable `debugMode` + `writeDebugFile` in the
  plugin settings → `/tmp/dreamplex.log`; GUI crashlogs live in
  `/home/root/logs/`.

Known limitations
-----------------

* Plex servers with *Secure connections: Required* and no local-network
  exemption are not supported (the plugin talks plain `http` to the PMS;
  API redirects to https are followed, playback is not).
* The `/library/sections/<id>/search?type=N` endpoint is kept for the Search
  entries; on servers where it ever disappears the search entry would come
  back empty (the filter/browse entries are unaffected).
* **Some boxes/networks cannot reach plex.tv reliably.** plex.tv is a
  round-robin of AWS IPs; on some networks part of that pool is
  unreachable or the connection is flaky, so a *plex.tv* connection type
  can time out (the box's plain TLS to other hosts is fine — this is
  network reachability to plex.tv, not OpenSSL). The plugin now retries and
  reports the error instead of crashing. Reliable workaround: use an
  **IP/DNS** connection to the server with the **Access Token** field
  filled — direct HTTP to the PMS is unaffected.

Development
-----------

Offline test suite (no receiver, no PMS needed — a mock server is included):

    py -3 -m unittest discover -s tests
    py -3 tools/run_checks.py       # byte-compile + py2-syntax gate

Skins (big thanks to the skinners :-)
-------------------------------------

* Blockbuster — http://www.vuplus-support.org/wbb3/index.php?page=Thread&threadID=69568
* YouPlex-Blue/Green/Purple/Red, Plex_Experience — https://github.com/OpenViX/DreamPlexSkins

License and attribution
-----------------------

GPL-2 (see `src/LICENSE.txt`), like the original. DreamPlex was written by
**DonDavici** (2012), ported to Python 3 and maintained by **jbleyel** and
the **oe-alliance** / OpenViX teams, with parts based on hippojay's plexbmc.
This fork only fixes compatibility with modern Plex Media Server releases;
all credit for the plugin itself belongs to the original authors.

The modern-PMS fixes in this fork - root-cause analysis against a live
server, the offline test harness, the fixes themselves and the on-receiver
verification - were researched, implemented and tested by **Claude**
(Anthropic's Claude Fable 5 model), directed by **jrodzar**. Every commit
carries the corresponding `Co-Authored-By` trailer.
