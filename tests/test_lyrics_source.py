import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import lyrics_source as ls
import riftkit

# Made-up lyrics only.
LRC = """\
[ar:Nobody]
[ti:Teapot Song]
[00:05.10] The blue kettle sings at noon
[00:09.50] We walk the long road home
[00:14.00]
"""


def fake_lrclib(monkeypatch, status=200, doc=None):
    """Stand-in for the network; records every URL requested."""
    calls = []

    def get(url, timeout=15.0):
        calls.append(url)
        return status, json.dumps(doc) if doc is not None else ""

    monkeypatch.setattr(ls, "_http_get", get)
    return calls


# --- LRC parsing -------------------------------------------------------------

def test_parse_lrc_reads_times_and_ignores_tag_lines():
    assert ls.parse_lrc(LRC) == [
        (5.1, "The blue kettle sings at noon"),
        (9.5, "We walk the long road home"),
        (14.0, ""),
    ]


def test_parse_lrc_handles_repeated_timestamps_and_whole_seconds():
    entries = ls.parse_lrc("[00:30][01:02.50]Hum along\n[00:10.25]First")
    assert entries == [(10.25, "First"), (30.0, "Hum along"), (62.5, "Hum along")]


def test_lrc_to_segments_ends_each_line_at_the_next_and_drops_the_end_marker():
    segments = ls.lrc_to_segments(LRC)
    assert [(s["start"], s["end"], s["text"]) for s in segments] == [
        (5.1, 9.5, " The blue kettle sings at noon"),
        (9.5, 14.0, " We walk the long road home"),
    ]
    assert all(s["words"] == [] for s in segments)


def test_last_line_without_end_marker_ends_at_song_end_or_after_a_few_seconds():
    text = "[00:05.00]Only line"
    assert ls.lrc_to_segments(text, last_end=60.0)[0]["end"] == 60.0
    assert ls.lrc_to_segments(text)[0]["end"] == 5.0 + ls.LAST_LINE_SECONDS


# --- Offset ------------------------------------------------------------------

def test_offset_shifts_every_line_and_word_but_not_below_zero():
    segments = [
        {"start": 0.2, "end": 1.0, "text": " a", "words": [{"word": " a", "start": 0.2, "end": 1.0}]},
        {"start": 5.0, "end": 6.0, "text": " b", "words": []},
    ]
    shifted = ls.shift_segments(segments, -0.5)
    assert [(s["start"], s["end"]) for s in shifted] == [(0.0, 0.5), (4.5, 5.5)]
    assert shifted[0]["words"][0]["start"] == 0.0 and shifted[0]["words"][0]["end"] == 0.5
    assert segments[1]["start"] == 5.0  # the input is left alone


# --- Choosing by duration ----------------------------------------------------

def test_lrclib_result_within_two_seconds_is_used_with_one_request(monkeypatch):
    calls = fake_lrclib(monkeypatch, doc={"duration": 181.0, "syncedLyrics": LRC})
    assert ls.fetch_lrclib("Nobody", "Teapot Song", 180.4) == LRC
    assert len(calls) == 1
    assert "artist_name=Nobody" in calls[0] and "track_name=Teapot+Song" in calls[0]
    assert "duration=180" in calls[0]


@pytest.mark.parametrize("doc,status", [
    ({"duration": 183.0, "syncedLyrics": LRC}, 200),    # 2.6 s off
    ({"duration": 180.0, "syncedLyrics": None}, 200),   # plain lyrics only
    ({"duration": 180.0, "plainLyrics": "words"}, 200),
    (None, 404),                                         # not found
])
def test_lrclib_result_is_rejected_without_synced_lyrics_or_with_wrong_duration(monkeypatch, doc, status):
    fake_lrclib(monkeypatch, status=status, doc=doc)
    assert ls.fetch_lrclib("Nobody", "Teapot Song", 180.4) is None


# --- Order of sources --------------------------------------------------------

def test_lrc_next_to_the_song_wins_and_the_network_is_not_used(tmp_path, monkeypatch):
    song = tmp_path / "Teapot Song.opus"
    song.touch()
    (tmp_path / "Teapot Song.lrc").write_text(LRC, encoding="utf-8")
    calls = fake_lrclib(monkeypatch, doc={"duration": 20.0, "syncedLyrics": "[00:01.00]other"})

    segments, note = ls.find_lyrics(song, "auto", artist="Nobody", title="Teapot Song", duration=20.0)
    assert segments[0]["text"] == " The blue kettle sings at noon"
    assert "Teapot Song.lrc" in note
    assert calls == []


def test_lrclib_result_is_saved_next_to_the_song_and_not_fetched_twice(tmp_path, monkeypatch):
    song = tmp_path / "Teapot Song.opus"
    song.touch()
    calls = fake_lrclib(monkeypatch, doc={"duration": 20.0, "syncedLyrics": LRC})

    first, note = ls.find_lyrics(song, "auto", artist="Nobody", title="Teapot Song", duration=20.0)
    assert note.startswith("LRCLIB")
    assert (tmp_path / "Teapot Song.lrc").read_text(encoding="utf-8") == LRC

    second, note = ls.find_lyrics(song, "auto", artist="Nobody", title="Teapot Song", duration=20.0)
    assert second == first
    assert "Teapot Song.lrc" in note
    assert len(calls) == 1


def test_auto_falls_back_to_hearing_when_nothing_is_found(tmp_path, monkeypatch):
    song = tmp_path / "Teapot Song.opus"
    song.touch()
    fake_lrclib(monkeypatch, status=404)
    segments, note = ls.find_lyrics(song, "auto", artist="Nobody", title="Teapot Song", duration=20.0)
    assert segments is None and "LRCLIB" in note


def test_auto_skips_lrclib_without_artist_and_title(tmp_path, monkeypatch):
    song = tmp_path / "Teapot Song.opus"
    song.touch()
    calls = fake_lrclib(monkeypatch, doc={"duration": 20.0, "syncedLyrics": LRC})
    segments, note = ls.find_lyrics(song, "auto", duration=20.0)
    assert segments is None and "--artist" in note
    assert calls == []


def test_explicit_lrc_source_does_not_use_lrclib(tmp_path, monkeypatch):
    song = tmp_path / "Teapot Song.opus"
    song.touch()
    calls = fake_lrclib(monkeypatch, doc={"duration": 20.0, "syncedLyrics": LRC})
    segments, note = ls.find_lyrics(song, "lrc", artist="Nobody", title="Teapot Song", duration=20.0)
    assert segments is None and "no .lrc" in note
    assert calls == []


# --- Through riftkit.main ----------------------------------------------------

def _song_with_stems(tmp_path):
    song = tmp_path / "Teapot Song.opus"
    song.touch()
    stems_dir = tmp_path / "out" / "htdemucs_ft" / "Teapot Song"
    stems_dir.mkdir(parents=True)
    for name in ("vocals", "drums", "bass", "other"):
        (stems_dir / f"{name}.wav").touch()
    return song, stems_dir


def _run_main(song, tmp_path, *extra):
    transcribe = MagicMock(return_value=False)
    argv = ["riftkit.py", str(song), "--output", str(tmp_path / "out"), *extra]
    with patch("sys.argv", argv), \
         patch("riftkit.subprocess.run", return_value=MagicMock(returncode=0, stdout="{}")), \
         patch("riftkit.probe_duration", return_value=20.0), \
         patch("riftkit.transcribe_vocals", transcribe), \
         patch("reaper_project.media_duration", return_value=20.0):
        riftkit.main()
    return transcribe


def test_main_uses_lrc_next_to_song_and_applies_the_offset(tmp_path, capsys):
    song, stems_dir = _song_with_stems(tmp_path)
    (tmp_path / "Teapot Song.lrc").write_text(LRC, encoding="utf-8")

    transcribe = _run_main(song, tmp_path, "--lyrics-offset", "-0.6")

    transcribe.assert_not_called()
    doc = json.loads((stems_dir / "lyrics.json").read_text(encoding="utf-8"))
    assert [round(s["start"], 2) for s in doc["segments"]] == [4.5, 8.9]
    project = (stems_dir / "Teapot Song.RPP").read_text()
    assert 'NAME "Lyrics"' in project and "The blue kettle sings at noon" in project
    out = capsys.readouterr().out
    assert "Lyrics source: .lrc file next to the song" in out
    assert "shifted by -0.6 s" in out


def test_main_falls_back_to_hearing_when_lrclib_has_nothing(tmp_path, monkeypatch, capsys):
    song, _ = _song_with_stems(tmp_path)
    fake_lrclib(monkeypatch, status=404)

    transcribe = _run_main(song, tmp_path, "--artist", "Nobody", "--title", "Teapot Song")

    transcribe.assert_called_once()
    assert "Lyrics source: heard" in capsys.readouterr().out


def test_main_lyrics_from_hear_never_looks_anything_up(tmp_path, monkeypatch):
    song, _ = _song_with_stems(tmp_path)
    (tmp_path / "Teapot Song.lrc").write_text(LRC, encoding="utf-8")
    calls = fake_lrclib(monkeypatch, doc={"duration": 20.0, "syncedLyrics": LRC})

    transcribe = _run_main(song, tmp_path, "--lyrics-from", "hear", "--artist", "Nobody", "--title", "Teapot Song")

    transcribe.assert_called_once()
    assert calls == []
