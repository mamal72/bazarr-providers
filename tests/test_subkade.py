import base64
import hashlib
import importlib.util
import io
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDER_DIR = ROOT / "providers" / "subkade"


def _load_provider_module():
    spec = importlib.util.spec_from_file_location(
        "subkade_provider", PROVIDER_DIR / "provider.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ParseEpisodesTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_provider_module()

    def test_standard_sxxeyy(self):
        self.assertEqual(self.mod.parse_episodes("Show.S04E09.720p.srt"), (4, {9}))

    def test_double_episode_covers_both(self):
        self.assertEqual(
            self.mod.parse_episodes("Show.S04E01E02.WEB-DL.srt"), (4, {1, 2})
        )

    def test_spaced_season_episode(self):
        self.assertEqual(self.mod.parse_episodes("Show - S04 E14.srt"), (4, {14}))

    def test_cross_notation(self):
        self.assertEqual(self.mod.parse_episodes("Show 4x07.srt"), (4, {7}))

    def test_no_episode_information(self):
        self.assertEqual(self.mod.parse_episodes("readme.txt"), (None, set()))


class ReleaseTagTests(unittest.TestCase):
    """The tag is what separates the two numbering schemes in one archive."""

    def setUp(self):
        self.mod = _load_provider_module()

    def test_quality_tag_is_release_named(self):
        self.assertTrue(self.mod.is_release_named("Show.S04E09.1080p.WEB-DL.srt"))
        self.assertTrue(self.mod.is_release_named("Show.S04E09.x265.srt"))

    def test_bare_name_is_not_release_named(self):
        self.assertFalse(self.mod.is_release_named("Show - S04 E14.srt"))


class ParseSeriesPageTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_provider_module()

    def test_picks_first_non_navigation_link(self):
        html = (
            '<a href="https://subkade.ir/category/series/">cat</a>'
            '<a href="https://subkade.ir/the-office/">The Office</a>'
        )
        self.assertEqual(
            self.mod.parse_series_page(html), "https://subkade.ir/the-office/"
        )

    def test_returns_none_when_only_navigation(self):
        html = '<a href="https://subkade.ir/about/">about</a>'
        self.assertIsNone(self.mod.parse_series_page(html))


class ParseArchivesTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_provider_module()

    def test_maps_seasons_to_archives(self):
        html = (
            'x https://dl1.subkade.ir/sub/The.Office.S04.zip y '
            'https://dl2.subkade.ir/sub/The.Office.S05.zip z'
        )
        archives = self.mod.parse_archives(html)
        self.assertEqual(sorted(archives), [4, 5])
        self.assertTrue(archives[4].endswith("S04.zip"))

    def test_unseasoned_archive_becomes_season_zero(self):
        html = 'https://dl1.subkade.ir/sub/Some.Movie.2019.zip'
        self.assertEqual(list(self.mod.parse_archives(html)), [0])


class SelectMembersTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_provider_module()

    def test_matches_release_named_and_bare_on_the_same_number(self):
        """Archives use the same numbering Bazarr does, so both spellings match."""
        members = self.mod.select_members(
            ["Show.S04E09.1080p.WEB-DL.srt", "Show - S04 E09.srt"],
            season=4, episode=9,
        )
        self.assertEqual(len(members), 2)

    def test_release_named_sorts_before_bare(self):
        members = self.mod.select_members(
            ["Show - S04 E09.srt", "Show.S04E09.720p.HDTV.srt"], season=4, episode=9
        )
        self.assertEqual(members[0][0], "Show.S04E09.720p.HDTV.srt")

    def test_two_part_episode_matches_either_half(self):
        """S04E01E02 is filed under E01 and covers both numbers."""
        for wanted in (1, 2):
            members = self.mod.select_members(
                ["Show.S04E01E02.1080p.WEB-DL.srt"], season=4, episode=wanted
            )
            self.assertEqual(len(members), 1, "episode %d should match" % wanted)

    def test_other_episodes_excluded(self):
        members = self.mod.select_members(
            ["Show.S04E05.720p.srt"], season=4, episode=9
        )
        self.assertEqual(members, [])

    def test_non_subtitle_and_directories_ignored(self):
        members = self.mod.select_members(
            ["Season 4/", "notes.txt", "Show.S04E09.720p.srt"], season=4, episode=9
        )
        self.assertEqual(len(members), 1)

    def test_wrong_season_excluded(self):
        members = self.mod.select_members(
            ["Show.S05E09.720p.srt"], season=4, episode=9
        )
        self.assertEqual(members, [])




class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_provider_module()

    def _archive_bytes(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("Show.S04E09.720p.srt", "1\n00:00:01,000 --> 00:00:02,000\nسلام\n")
        return buffer.getvalue()

    def test_download_returns_hashed_base64_content(self):
        provider = self.mod.SubkadeProvider()
        blob = self._archive_bytes()
        provider._archive_cache["https://dl1.subkade.ir/x.zip"] = blob

        result = provider.download(
            {"archive_url": "https://dl1.subkade.ir/x.zip",
             "member": "Show.S04E09.720p.srt"},
            {"alpha3": "fas"}, {},
        )
        self.assertFalse(result["empty"])
        self.assertEqual(result["format"], "srt")
        content = base64.b64decode(result["content_b64"])
        self.assertEqual(hashlib.sha256(content).hexdigest(), result["content_sha256"])
        self.assertIn("سلام", content.decode("utf-8"))

    def test_missing_payload_is_empty(self):
        provider = self.mod.SubkadeProvider()
        self.assertEqual(provider.download({}, {"alpha3": "fas"}, {}), {"empty": True})


class LiveCaptureTests(unittest.TestCase):
    """Parsers run against real captures from subkade.ir.

    Committed fixtures rather than live requests: the parsers must keep working
    against the markup the site actually serves, without CI depending on it
    being reachable.
    """

    FIXTURES = ROOT / "tests" / "fixtures"

    def setUp(self):
        self.mod = _load_provider_module()

    def test_finds_series_page_in_real_search_html(self):
        html = (self.FIXTURES / "subkade_search_tt0386676.html").read_text()
        page = self.mod.parse_series_page(html)
        self.assertIsNotNone(page)
        self.assertIn("the-office", page)

    def test_finds_every_season_archive_on_real_series_page(self):
        html = (self.FIXTURES / "subkade_series_the_office.html").read_text()
        archives = self.mod.parse_archives(html)
        self.assertEqual(sorted(archives), list(range(1, 10)))
        self.assertIn("S04-Complete", archives[4])

    def test_real_archive_matches_the_right_episode(self):
        """Folder E09 holds S04E09 'Local Ad' - the archive uses TVDB numbers."""
        import json
        names = json.loads((self.FIXTURES / "subkade_s04_namelist.json").read_text())
        picked = self.mod.select_members(names, season=4, episode=9)
        chosen = [name for _, name in picked]
        self.assertTrue(chosen, "expected matches for S04E09")
        self.assertTrue(self.mod.is_release_named(chosen[0]))
        self.assertIn("S04E09", chosen[0])
        # nothing from a neighbouring episode leaks in
        self.assertFalse(any("E05" in n or "E07" in n for n in chosen))

    def test_real_archive_two_part_episode(self):
        """S04E01E02 lives in the E01 folder and answers for both halves."""
        import json
        names = json.loads((self.FIXTURES / "subkade_s04_namelist.json").read_text())
        for wanted in (1, 2):
            picked = self.mod.select_members(names, season=4, episode=wanted)
            self.assertTrue(picked, "episode %d should match" % wanted)

    def test_directories_and_url_files_never_selected(self):
        import json
        names = json.loads((self.FIXTURES / "subkade_s04_namelist.json").read_text())
        picked = self.mod.select_members(names, season=4, episode=1)
        for member, _ in picked:
            self.assertFalse(member.endswith("/"))
            self.assertTrue(member.lower().endswith(SUB_EXTS))


SUB_EXTS = (".srt", ".ass", ".ssa")


if __name__ == "__main__":
    unittest.main()
