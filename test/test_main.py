from unittest.mock import patch, MagicMock

from yatvr.main import (
    process_video,
    process_file,
    rename_episode,
    ShowInfo,
)

SHOW_INFO = ShowInfo(id=12345, name="Breaking Bad", year=2008)


def make_episode_mock(title: str):
    """Return a mock for tmdb.TV_Episodes(...) that returns the given episode title."""
    mock_episode = MagicMock()
    mock_episode.info.return_value = {"name": title}
    return mock_episode


# ---------------------------------------------------------------------------
# rename_episode — tests for the file-renaming logic
# ---------------------------------------------------------------------------


class TestRenameEpisode:
    def test_renames_file_to_correct_format(self, tmp_path):
        f = tmp_path / "breaking.bad.s01e01.mkv"
        f.touch()

        with patch("yatvr.main.tmdb.TV_Episodes", return_value=make_episode_mock("Pilot")):
            rename_episode(f, SHOW_INFO, season=1, episode=1)

        assert (tmp_path / "s01e01 - Pilot.mkv").exists()
        assert not f.exists()

    def test_extension_lowercased(self, tmp_path):
        f = tmp_path / "episode.S02E03.MKV"
        f.touch()

        with patch(
            "yatvr.main.tmdb.TV_Episodes", return_value=make_episode_mock("Bit by a Dead Bee")
        ):
            rename_episode(f, SHOW_INFO, season=2, episode=3)

        assert (tmp_path / "s02e03 - Bit by a Dead Bee.mkv").exists()

    def test_slash_in_title_replaced(self, tmp_path):
        f = tmp_path / "episode.s01e02.mp4"
        f.touch()

        with patch(
            "yatvr.main.tmdb.TV_Episodes", return_value=make_episode_mock("Cat/Mouse")
        ):
            rename_episode(f, SHOW_INFO, season=1, episode=2)

        assert (tmp_path / "s01e02 - Cat - Mouse.mp4").exists()

    def test_already_correct_name_not_renamed(self, tmp_path):
        f = tmp_path / "s03e07 - One Minute.mkv"
        f.touch()

        with patch(
            "yatvr.main.tmdb.TV_Episodes", return_value=make_episode_mock("One Minute")
        ):
            rename_episode(f, SHOW_INFO, season=3, episode=7)

        # File should still be there under the same name
        assert (tmp_path / "s03e07 - One Minute.mkv").exists()

    def test_missing_season_prints_error_and_skips(self, tmp_path, capsys):
        f = tmp_path / "episode.mkv"
        f.touch()

        with patch("yatvr.main.tmdb.TV_Episodes") as mock_ep:
            rename_episode(f, SHOW_INFO, season=None, episode=1)
            mock_ep.assert_not_called()

        captured = capsys.readouterr()
        assert "ERROR" in captured.out
        assert f.exists()  # file untouched

    def test_season_and_episode_zero_padded(self, tmp_path):
        f = tmp_path / "s09e09.mkv"
        f.touch()

        with patch("yatvr.main.tmdb.TV_Episodes", return_value=make_episode_mock("Felina")):
            rename_episode(f, SHOW_INFO, season=9, episode=9)

        assert (tmp_path / "s09e09 - Felina.mkv").exists()


# ---------------------------------------------------------------------------
# process_video — tests for filename parsing + rename dispatch
# ---------------------------------------------------------------------------


class TestProcessVideo:
    """
    Each test creates a real file and patches rename_video so we can
    assert what show_name / season / episode were parsed from the path.
    """

    def _run(self, tmp_path, rel_path: str):
        """Create the file at rel_path inside tmp_path and run process_video."""
        f = tmp_path / rel_path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.touch()
        calls = []
        with patch("yatvr.main.rename_video", side_effect=lambda *a, **kw: calls.append(a)):
            process_video(f)
        return calls

    # ---- show name + season from directory path ----

    def test_show_year_season_dir_sxxexx_filename(self, tmp_path):
        calls = self._run(tmp_path, "Breaking Bad (2008)/Season 1/s01e01 - Pilot.mkv")
        assert len(calls) == 1
        _file, show_name, year, season, episode = calls[0]
        assert show_name == "Breaking Bad"
        assert year == "2008"
        assert season == 1
        assert episode == 1

    def test_show_season_dir_sxxexx_filename(self, tmp_path):
        calls = self._run(tmp_path, "The Wire/Season 3/s03e10 -MiddleGround.mkv")
        assert len(calls) == 1
        _file, show_name, year, season, episode = calls[0]
        assert show_name == "The Wire"
        assert year is None
        assert season == 3
        assert episode == 10

    def test_sxxexx_in_filename_with_season_dir(self, tmp_path):
        # show_name requires a 'Season N' directory; sXXeXX in the filename
        # provides the episode number (season already captured from the dir).
        calls = self._run(tmp_path, "Breaking Bad/Season 2/breaking.bad.s02e05.mkv")
        assert len(calls) == 1
        _file, show_name, year, season, episode = calls[0]
        assert show_name == "Breaking Bad"
        assert year is None
        assert season == 2
        assert episode == 5

    # ---- alternate episode notation ----

    def test_season_x_episode_format(self, tmp_path):
        """1x05 style notation."""
        calls = self._run(tmp_path, "The Office/Season 1/1x05.mkv")
        assert len(calls) == 1
        _file, show_name, year, season, episode = calls[0]
        assert show_name == "The Office"
        assert season == 1
        assert episode == 5

    def test_episode_word_format(self, tmp_path):
        """'Episode 3' style notation combined with directory-parsed season."""
        calls = self._run(tmp_path, "Seinfeld/Season 4/Episode 03.mkv")
        assert len(calls) == 1
        _file, show_name, year, season, episode = calls[0]
        assert show_name == "Seinfeld"
        assert season == 4
        assert episode == 3

    def test_part_word_format(self, tmp_path):
        """'Part 2' style notation combined with directory-parsed season."""
        calls = self._run(tmp_path, "Miniseries/Season 1/Part 2.mkv")
        assert len(calls) == 1
        _file, show_name, year, season, episode = calls[0]
        assert season == 1
        assert episode == 2

    def test_case_insensitive_sxxexx(self, tmp_path):
        # Season comes from the directory path; episode is parsed from the
        # uppercase S02E04 token in the filename via the case-insensitive regex.
        calls = self._run(tmp_path, "Show/Season 2/Show.S02E04.mkv")
        assert len(calls) == 1
        _file, show_name, year, season, episode = calls[0]
        assert season == 2
        assert episode == 4

    def test_unparseable_file_does_not_call_rename(self, tmp_path, capsys):
        calls = self._run(tmp_path, "random_video.mkv")
        assert calls == []
        captured = capsys.readouterr()
        assert "Error" in captured.out


# ---------------------------------------------------------------------------
# process_file — tests for directory recursion and extension filtering
# ---------------------------------------------------------------------------


class TestProcessFile:
    def test_non_video_file_skipped(self, tmp_path):
        f = tmp_path / "notes.txt"
        f.touch()

        with patch("yatvr.main.process_video") as mock_pv:
            process_file(f)
            mock_pv.assert_not_called()

    def test_video_file_processed(self, tmp_path):
        f = tmp_path / "s01e01.mkv"
        f.touch()

        with patch("yatvr.main.process_video") as mock_pv:
            process_file(f)
            mock_pv.assert_called_once_with(f)

    def test_all_video_extensions_accepted(self, tmp_path):
        extensions = [".mkv", ".m4v", ".mp4", ".avi", ".webm"]
        for ext in extensions:
            f = tmp_path / f"episode{ext}"
            f.touch()

        with patch("yatvr.main.process_video") as mock_pv:
            process_file(tmp_path)
            assert mock_pv.call_count == len(extensions)

    def test_video_extension_case_insensitive(self, tmp_path):
        f = tmp_path / "episode.MKV"
        f.touch()

        with patch("yatvr.main.process_video") as mock_pv:
            process_file(f)
            mock_pv.assert_called_once_with(f)

    def test_recurses_into_subdirectories(self, tmp_path):
        sub = tmp_path / "Season 1"
        sub.mkdir()
        f = sub / "s01e01.mkv"
        f.touch()

        with patch("yatvr.main.process_video") as mock_pv:
            process_file(tmp_path)
            mock_pv.assert_called_once_with(f)

    def test_mixed_directory_only_videos_processed(self, tmp_path):
        (tmp_path / "s01e01.mkv").touch()
        (tmp_path / "s01e02.mp4").touch()
        (tmp_path / "subtitles.srt").touch()
        (tmp_path / "info.nfo").touch()

        with patch("yatvr.main.process_video") as mock_pv:
            process_file(tmp_path)
            assert mock_pv.call_count == 2


# ---------------------------------------------------------------------------
# Integration — full pipeline with API mocked
# ---------------------------------------------------------------------------


class TestIntegration:
    """End-to-end: real files on disk, only TMDB API calls are mocked."""

    def test_full_rename_from_directory_path(self, tmp_path):
        season_dir = tmp_path / "Breaking Bad (2008)" / "Season 1"
        season_dir.mkdir(parents=True)
        f = season_dir / "breaking.bad.s01e01.mkv"
        f.touch()

        mock_show = ShowInfo(id=1396, name="Breaking Bad", year=2008)
        mock_ep = make_episode_mock("Pilot")

        with (
            patch("yatvr.main.find_matching_shows", return_value=mock_show),
            patch("yatvr.main.tmdb.TV_Episodes", return_value=mock_ep),
        ):
            process_file(f)

        assert (season_dir / "s01e01 - Pilot.mkv").exists()
        assert not f.exists()

    def test_full_rename_with_season_x_episode_notation(self, tmp_path):
        season_dir = tmp_path / "Seinfeld" / "Season 2"
        season_dir.mkdir(parents=True)
        f = season_dir / "2x01 - The Ex-Girlfriend.avi"
        f.touch()

        mock_show = ShowInfo(id=1400, name="Seinfeld", year=1989)
        mock_ep = make_episode_mock("The Ex-Girlfriend")

        with (
            patch("yatvr.main.find_matching_shows", return_value=mock_show),
            patch("yatvr.main.tmdb.TV_Episodes", return_value=mock_ep),
        ):
            process_file(f)

        assert (season_dir / "s02e01 - The Ex-Girlfriend.avi").exists()
