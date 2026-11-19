import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import lyrics_source as ls
import riffkit

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


# --- Through riffkit.main ----------------------------------------------------

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
    argv = ["riffkit.py", str(song), "--output", str(tmp_path / "out"), *extra]
    with patch("sys.argv", argv), \
         patch("riffkit.subprocess.run", return_value=MagicMock(returncode=0, stdout="{}")), \
         patch("riffkit.probe_duration", return_value=20.0), \
         patch("riffkit.transcribe_vocals", transcribe), \
         patch("reaper_project.media_duration", return_value=20.0):
        riffkit.main()
    return transcribe


def test_main_uses_lrc_next_to_song_and_applies_the_offset(tmp_path, capsys):
    song, stems_dir = _song_with_stems(tmp_path)
    (tmp_path / "Teapot Song.lrc").write_text(LRC, encoding="utf-8")

    transcribe = _run_main(song, tmp_path, "--lyrics-offset", "-0.6", "--no-word-times")

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


# --- Automatic offset --------------------------------------------------------

np = pytest.importorskip("numpy")


def _levels(voice_starts, length=60.0, line_seconds=1.5):
    """Synthetic 10 ms frame levels: quiet, with -20 dB singing at each start."""
    levels = np.full(int(length / ls.FRAME_SECONDS), -80.0)
    for t in voice_starts:
        a = int(t / ls.FRAME_SECONDS)
        levels[a:a + int(line_seconds / ls.FRAME_SECONDS)] = -20.0
    return levels


def _segments(starts):
    return [{"start": t, "end": t + 2.0, "text": " la"} for t in starts]


STARTS = [5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0]


def test_offset_is_measured_when_every_line_is_early_by_the_same_amount():
    offset, note = ls.measure_offset(_levels([t + 0.55 for t in STARTS]), _segments(STARTS))
    assert offset == pytest.approx(0.55)
    assert "8 of 8 lines" in note


def test_offset_can_be_negative_when_the_lyrics_are_late():
    offset, _ = ls.measure_offset(_levels([t - 0.4 for t in STARTS]), _segments(STARTS))
    assert offset == pytest.approx(-0.4)


def test_lyrics_already_in_time_are_left_alone():
    offset, note = ls.measure_offset(_levels([t + 0.03 for t in STARTS]), _segments(STARTS))
    assert offset is None and "already in time" in note


def test_no_offset_when_lines_disagree():
    jitter = [0.0, 1.0, -0.5, 0.9, -0.4, 1.1, 0.1, -0.3]
    offset, note = ls.measure_offset(_levels([t + j for t, j in zip(STARTS, jitter)]), _segments(STARTS))
    assert offset is None and "disagree" in note


def test_no_offset_without_enough_clear_voice_starts():
    offset, note = ls.measure_offset(_levels(STARTS[:3]), _segments(STARTS))
    assert offset is None and "too few" in note


def _main_with_lrc(tmp_path, *extra, measured=(0.55, "measured +0.55 s against the vocals (2 of 2 lines)")):
    song, stems_dir = _song_with_stems(tmp_path)
    (tmp_path / "Teapot Song.lrc").write_text(LRC, encoding="utf-8")
    with patch("lyrics_source.measure_offset_from_audio", return_value=measured) as measure:
        _run_main(song, tmp_path, *extra)
    doc = json.loads((stems_dir / "lyrics.json").read_text(encoding="utf-8"))
    return measure, [round(s["start"], 2) for s in doc["segments"]]


def test_main_applies_the_measured_offset_to_looked_up_lyrics(tmp_path, capsys):
    measure, starts = _main_with_lrc(tmp_path)
    measure.assert_called_once()
    assert starts == [5.65, 10.05]
    assert "Lyrics offset: measured +0.55 s" in capsys.readouterr().out


def test_main_explicit_offset_replaces_the_measurement(tmp_path):
    measure, starts = _main_with_lrc(tmp_path, "--lyrics-offset", "0")
    measure.assert_not_called()
    assert starts == [5.1, 9.5]


def test_main_does_not_measure_heard_lyrics(tmp_path):
    song, _ = _song_with_stems(tmp_path)
    with patch("lyrics_source.measure_offset_from_audio") as measure:
        _run_main(song, tmp_path, "--lyrics-from", "hear")
    measure.assert_not_called()


# --- Word times for text lyrics ----------------------------------------------
# Made-up words and made-up heard words.

def _line(text, start, end):
    return {"start": start, "end": end, "text": " " + text, "words": []}


def _starts(words):
    return [w["start"] for w in words]


def _increasing(words):
    return all(b > a for a, b in zip(_starts(words), _starts(words)[1:]))


def test_all_words_matched_take_the_heard_times():
    heard = [(10.2, " The"), (10.5, " blue"), (10.9, " kettle,"), (11.6, " sings!")]
    words, n = ls.time_line_words(_line("the Blue kettle sings", 10.0, 14.0), heard)
    assert n == 4
    assert [w["word"] for w in words] == [" the", " Blue", " kettle", " sings"]
    assert _starts(words) == [10.2, 10.5, 10.9, 11.6]


def test_missed_words_are_spread_between_matches_by_length():
    # "kettle" (6 letters) and "sings" (5) were misheard between "blue" and "at".
    heard = [(10.0, " the"), (10.4, " blue"), (11.0, " cattle"), (11.5, " springs"), (12.6, " at")]
    words, n = ls.time_line_words(_line("the blue kettle sings at", 10.0, 14.0), heard)
    assert n == 3
    # blue (4), kettle (6), sings (5) share 10.4 .. 12.6 (2.2 s over 15 letters)
    assert _starts(words) == pytest.approx([10.0, 10.4, 10.4 + 2.2 * 4 / 15, 10.4 + 2.2 * 10 / 15, 12.6], abs=0.001)
    assert _increasing(words)


def test_missed_words_at_the_start_and_end_fill_out_the_line():
    heard = [(11.0, " kettle")]
    words, n = ls.time_line_words(_line("the blue kettle sings", 10.0, 14.0), heard)
    assert n == 1
    assert words[0]["start"] == 10.0          # the first word starts with the line
    assert words[2]["start"] == 11.0
    assert 11.0 < words[3]["start"] < 14.0
    assert _increasing(words)


def test_a_line_with_no_matches_is_spread_evenly():
    heard = [(10.3, " something"), (11.0, " else")]
    words, n = ls.time_line_words(_line("we walk the road", 10.0, 14.0), heard)
    assert n == 0
    assert _starts(words) == [10.0, 11.0, 12.0, 13.0]


def test_repeated_chorus_lines_each_use_their_own_heard_words():
    heard = [(20.1, " la"), (20.6, " di"), (21.0, " da"),
             (30.3, " la"), (30.7, " di"), (31.2, " da")]
    segments = [_line("la di da", 20.0, 23.0), _line("la di da", 30.0, 33.0)]
    out, matched, spread = ls.add_word_times(segments, heard)
    assert (matched, spread) == (6, 0)
    assert _starts(out[0]["words"]) == [20.1, 20.6, 21.0]
    assert _starts(out[1]["words"]) == [30.3, 30.7, 31.2]


def test_heard_words_within_half_a_second_of_the_line_count():
    line = _line("hum along", 10.0, 12.0)
    # 0.4 s early: used, but the first word still starts with the line.
    words, n = ls.time_line_words(line, [(9.6, " hum"), (10.8, " along")])
    assert n == 2 and _starts(words) == [10.0, 10.8]
    # 0.6 s early or late: not used.
    words, n = ls.time_line_words(line, [(9.4, " hum"), (12.6, " along")])
    assert n == 0


def test_times_always_increase_even_when_heard_times_bunch_up():
    heard = [(10.5, " one"), (10.5, " two"), (10.5, " three"), (10.5, " four")]
    words, n = ls.time_line_words(_line("one two three four five", 10.0, 11.0), heard)
    assert n == 4
    assert words[0]["start"] >= 10.0
    assert _increasing(words)


def test_word_times_keep_line_times_and_text():
    segments = [_line("the blue kettle", 5.0, 9.0)]
    out, _, _ = ls.add_word_times(segments, [(5.2, " blue")])
    assert (out[0]["start"], out[0]["end"], out[0]["text"]) == (5.0, 9.0, " the blue kettle")
    assert segments[0]["words"] == []  # the input is left alone


def test_heard_words_reads_a_transcript_in_time_order():
    doc = {"segments": [
        {"words": [{"word": " b", "start": 2.0, "end": 2.5}, {"word": " ", "start": 2.6}]},
        {"words": [{"word": " a", "start": 1.0, "end": 1.5}]},
    ]}
    assert ls.heard_words(doc) == [(1.0, " a"), (2.0, " b")]


def test_normalize_matches_compare_lyrics():
    import importlib.util
    import sys
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("compare_lyrics", root / "scripts" / "compare_lyrics.py")
    cl = importlib.util.module_from_spec(spec)
    sys.modules["compare_lyrics"] = cl
    spec.loader.exec_module(cl)
    for text in ["Don't STOP, 'til dawn!", "rock-n-roll  ...  O'Malley's", "  "]:
        assert ls.normalize(text) == cl.normalize(text)


def test_main_hears_the_vocals_for_word_times_of_looked_up_lyrics(tmp_path, capsys):
    song, stems_dir = _song_with_stems(tmp_path)
    (tmp_path / "Teapot Song.lrc").write_text(LRC, encoding="utf-8")

    def fake_transcribe(vocals, output, model="medium"):
        assert vocals.name == "vocals.wav"
        Path(output).write_text(json.dumps({"segments": [{"words": [
            {"word": " blue", "start": 5.6}, {"word": " kettle", "start": 6.0},
            {"word": " walk", "start": 10.2},
        ]}]}), encoding="utf-8")
        return True

    with patch("sys.argv", ["riffkit.py", str(song), "--output", str(tmp_path / "out"),
                            "--lyrics-offset", "0"]), \
         patch("riffkit.subprocess.run", return_value=MagicMock(returncode=0, stdout="{}")), \
         patch("riffkit.probe_duration", return_value=20.0), \
         patch("riffkit.transcribe_vocals", side_effect=fake_transcribe) as transcribe, \
         patch("reaper_project.media_duration", return_value=20.0):
        riffkit.main()

    transcribe.assert_called_once()
    doc = json.loads((stems_dir / "lyrics.json").read_text(encoding="utf-8"))
    first = doc["segments"][0]
    assert (first["start"], first["text"]) == (5.1, " The blue kettle sings at noon")
    assert [w["start"] for w in first["words"]][1:3] == [5.6, 6.0]
    assert "Word times: 3 of 12 words took heard times, 9 spread" in capsys.readouterr().out


def test_main_no_word_times_keeps_line_times_only(tmp_path):
    song, stems_dir = _song_with_stems(tmp_path)
    (tmp_path / "Teapot Song.lrc").write_text(LRC, encoding="utf-8")
    transcribe = _run_main(song, tmp_path, "--lyrics-offset", "0", "--no-word-times")
    transcribe.assert_not_called()
    doc = json.loads((stems_dir / "lyrics.json").read_text(encoding="utf-8"))
    assert all(s["words"] == [] for s in doc["segments"])
