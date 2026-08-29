# coding=utf-8
"""SubKade (subkade.ir) provider — Persian subtitles, distributed per season.

SubKade publishes one archive per season rather than per-episode files, so this
provider resolves the series by IMDB id, downloads the season archive once,
caches it for the life of the worker, and serves the matching entry.

Archives are numbered the same way Bazarr numbers episodes: a two-part episode
is filed under its first number (S04E01E02 lives in the E01 folder), so no
translation is needed.

Standard library only: the Provider Hub runs plugins under `python -I` in an
isolated venv, so requests/subliminal/babelfish are unavailable by design.
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
import re
import urllib.parse
import urllib.request
import zipfile

BASE = "https://subkade.ir"
SUB_EXT = (".srt", ".ass", ".ssa")
HTTP_TIMEOUT_SECONDS = 30
ARCHIVE_TIMEOUT_SECONDS = 120
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Site chrome that must never be mistaken for a search hit.
NAV = (
    "/music-video/", "/about/", "/contact/", "/donate/", "/dmca/", "/account/",
    "/category/", "/tag/", "/author/", "/page/", "/login/", "/collection/",
    "/academy/", "/upload/", "/wp-json/", "/wp-content/", "/faq/", "/request/",
)

# Release-group builds always advertise a resolution or source; the bare
# "Show - S04 E09.srt" files never do, and that is exactly the split between
# the two numbering conventions inside a single subkade archive.
_RELEASE_TAG = re.compile(
    r"(?i)\b(\d{3,4}p|web-?dl|web-?rip|bluray|hdtv|x26[45]|hevc|amzn|dd[p+]?\d)\b"
)

_ARCHIVE_RE = re.compile(
    r"https?://dl\d*\.subkade\.ir/[^\"'\s<>]+?\.(?:zip|rar)"
)


# --------------------------------------------------------------------------
# pure helpers (unit-tested against fixtures, no network)
# --------------------------------------------------------------------------

def parse_episodes(name):
    """Return (season, {episode numbers}) declared by a subtitle filename.

    Handles the three shapes seen in subkade archives:
      S04E01      -> (4, {1})
      S04E01E02   -> (4, {1, 2})   double episode: covers BOTH
      "S04 E01" / 4x01 -> (4, {1})
    """
    match = re.search(r"[Ss](\d{1,2})((?:[\s._-]*[Ee]\d{1,3})+)", name)
    if match:
        season = int(match.group(1))
        episodes = {int(x) for x in re.findall(r"[Ee](\d{1,3})", match.group(2))}
        if episodes:
            return season, episodes
    match = re.search(r"(?:^|\D)(\d{1,2})[xX](\d{1,3})(?:\D|$)", name)
    if match:
        return int(match.group(1)), {int(match.group(2))}
    return None, set()


def parse_series_page(html_text):
    """First non-navigation subkade.ir link on a search results page."""
    for match in re.finditer(r'href="(%s/([^"?#]+))"' % re.escape(BASE), html_text):
        url, slug = match.group(1), match.group(2)
        if any(nav in url for nav in NAV) or not slug.strip("/"):
            continue
        return url
    return None


def parse_archives(html_text):
    """season number -> archive url. Season 0 means 'single archive' (movie)."""
    out = {}
    for url in sorted(set(_ARCHIVE_RE.findall(html_text))):
        filename = url.rsplit("/", 1)[-1]
        match = (re.search(r"[._-][Ss](\d{1,2})(?:[._-]|$)", filename)
                 or re.search(r"[Ss](\d{1,2})", filename))
        out.setdefault(int(match.group(1)) if match else 0, url)
    return out


def is_release_named(name):
    """True when the filename carries a quality/source tag.

    Only used for ranking: an entry naming its release lets Bazarr score the
    match against the video, so it is offered ahead of a bare filename.
    """
    return bool(_RELEASE_TAG.search(name))


def select_members(namelist, season, episode):
    """Entries in the archive that match the requested episode.

    Release-named entries are returned first: they carry the release string
    Bazarr scores against, so they are the better pick when both are present.
    """
    scored = []
    for member in namelist:
        if member.endswith("/") or not member.lower().endswith(SUB_EXT):
            continue
        name = os.path.basename(member)
        if episode is None:                      # movie: single archive, take all
            scored.append((1, member, name))
            continue
        found_season, episodes = parse_episodes(name)
        if found_season is not None and season is not None and found_season != season:
            continue
        if episode not in episodes:
            continue
        scored.append((0 if is_release_named(name) else 1, member, name))
    scored.sort(key=lambda item: item[0])
    return [(member, name) for _, member, name in scored]




def _alpha3_of(language):
    if isinstance(language, dict):
        return (language.get("alpha3") or "").lower()
    return str(language or "").lower()


# --------------------------------------------------------------------------
# provider
# --------------------------------------------------------------------------

class SubkadeProvider:
    """Persian subtitles from subkade.ir."""

    def __init__(self):
        self._archive_cache = {}
        self._page_cache = {}

    # -- http -------------------------------------------------------------
    def _http_get(self, url, timeout=HTTP_TIMEOUT_SECONDS):
        request = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
        })
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()

    def _series_page(self, imdb_id):
        if imdb_id not in self._page_cache:
            body = self._http_get("%s/?s=%s" % (BASE, urllib.parse.quote(imdb_id)))
            self._page_cache[imdb_id] = parse_series_page(
                body.decode("utf-8", "replace"))
        return self._page_cache[imdb_id]

    def _archive(self, url):
        if url not in self._archive_cache:
            self._archive_cache[url] = self._http_get(
                url, timeout=ARCHIVE_TIMEOUT_SECONDS)
        return self._archive_cache[url]

    # -- Provider Hub API --------------------------------------------------
    def search(self, video, languages, config):
        if not any(_alpha3_of(item) == "fas" for item in (languages or [])):
            return []

        imdb_id = video.get("series_imdb_id") or video.get("imdb_id")
        if not imdb_id:
            return []

        page_url = self._series_page(imdb_id)
        if not page_url:
            return []

        archives = parse_archives(
            self._http_get(page_url).decode("utf-8", "replace"))
        if not archives:
            return []

        is_episode = video.get("kind") == "episode" and video.get("episode") is not None
        season = video.get("season") if is_episode else 0
        archive_url = archives.get(season) or (None if is_episode else archives.get(0))
        if not archive_url:
            return []

        try:
            archive = zipfile.ZipFile(io.BytesIO(self._archive(archive_url)))
        except zipfile.BadZipFile:
            # subkade also publishes .rar, which the stdlib cannot read.
            return []

        members = select_members(
            archive.namelist(),
            season if is_episode else None,
            video.get("episode") if is_episode else None,
        )

        results = []
        for member, name in members:
            results.append({
                "provider": "subkade",
                "id": "%s#%s" % (archive_url, member),
                "language": {"alpha3": "fas", "hi": False, "forced": False},
                "release_info": name,
                "filename": name,
                "hash_verifiable": False,
                "hearing_impaired": False,
                "hearing_impaired_verifiable": False,
                "display": {"page_link": page_url},
                "provider_payload": {
                    "archive_url": archive_url,
                    "member": member,
                },
            })
        return results

    def download(self, provider_payload, language, config):
        payload = provider_payload or {}
        archive_url = payload.get("archive_url")
        member = payload.get("member")
        if not archive_url or not member:
            return {"empty": True}

        with zipfile.ZipFile(io.BytesIO(self._archive(archive_url))) as archive:
            content = archive.read(member)

        if not content:
            return {"empty": True}
        return {
            "content_b64": base64.b64encode(content).decode("ascii"),
            "content_sha256": hashlib.sha256(content).hexdigest(),
            "format": os.path.splitext(member)[1].lstrip(".").lower() or "srt",
            "empty": False,
        }
