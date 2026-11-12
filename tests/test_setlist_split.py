from pathlib import Path
from unittest.mock import patch

import pytest

np = pytest.importorskip("numpy")

import riftkit
import setlist_split as ss

FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOTHENBURG = FIXTURES_DIR / "gothenburg"


# ---------------------------------------------------------------------------
# parse_setlist
# ---------------------------------------------------------------------------

def test_parse_setlist_reads_gothenburg_fixture():
    titles = ss.parse_setlist(GOTHENBURG / "setlist.txt")
    assert len(titles) == 13
    assert titles[0] == "Spanish Castle Magic"
    assert titles[4] == "Hey Baby"
    assert titles[-1] == "Voodoo Child (Slight Return)"


def test_parse_setlist_ignores_concert_header_lines(tmp_path):
    f = tmp_path / "setlist.txt"
    f.write_text(
        "Some Band - Live Somewhere\nDate: 1970\nVenue: A Park\n\n"
        "Setlist, in order:\nFirst Song\nSecond Song\n"
    )
    assert ss.parse_setlist(f) == ["First Song", "Second Song"]


def test_parse_setlist_plain_titles(tmp_path):
    f = tmp_path / "setlist.txt"
    f.write_text("First Song\n\nSecond Song\nThird Song\n")
    assert ss.parse_setlist(f) == ["First Song", "Second Song", "Third Song"]


# ---------------------------------------------------------------------------
# find_breaks
# ---------------------------------------------------------------------------

def _level(*blocks):
    """Build a 10 Hz level curve from (seconds, dB) blocks."""
    return np.concatenate([np.full(int(seconds * 10), float(db)) for seconds, db in blocks])


def test_find_breaks_cuts_before_the_band_comes_back():
    level = _level((100, -10), (8, -40), (100, -10))
    breaks = [b for b in ss.find_breaks(level) if b.kind == "break"]
    assert len(breaks) == 1
    assert breaks[0].start == pytest.approx(100.0, abs=0.5)
    assert breaks[0].end == pytest.approx(108.0, abs=0.5)
    assert breaks[0].cut == pytest.approx(105.0, abs=0.5)  # 3 s pre-roll


def test_find_breaks_merges_dips_separated_by_short_noise():
    # applause burst (4 s, not full volume) in the middle of one break
    level = _level((100, -10), (5, -35), (4, -16), (5, -40), (100, -10))
    breaks = [b for b in ss.find_breaks(level) if b.kind == "break"]
    assert len(breaks) == 1
    assert breaks[0].cut == pytest.approx(111.0, abs=0.6)  # in the deeper, later dip


def test_find_breaks_treats_short_full_volume_burst_as_previous_songs_ending():
    # song ... pause ... 8 s final flourish at full volume ... short dip ... next song
    level = _level((100, -10), (4, -40), (8, -10), (1.5, -30), (100, -10))
    breaks = [b for b in ss.find_breaks(level) if b.kind == "break"]
    assert len(breaks) == 1
    assert breaks[0].cut == pytest.approx(112.0, abs=0.6)  # after the flourish, not at 100


def test_find_breaks_ignores_blips_shorter_than_minimum():
    level = _level((100, -10), (1, -40), (100, -10))
    assert [b for b in ss.find_breaks(level) if b.kind == "break"] == []


def test_find_breaks_reports_lull_only_where_no_break():
    level = _level((100, -10), (6, -17), (100, -10), (6, -40), (100, -10))
    found = ss.find_breaks(level)
    assert [b.kind for b in found] == ["lull", "break"]
    assert found[0].score < found[1].score


# ---------------------------------------------------------------------------
# find_changes
# ---------------------------------------------------------------------------

def test_find_changes_finds_shift_in_tone_balance():
    bassy = np.tile([0.7, 0.2, 0.05, 0.03, 0.02], (60, 1))
    bright = np.tile([0.2, 0.2, 0.2, 0.2, 0.2], (60, 1))
    changes = ss.find_changes(np.vstack([bassy, bright]))
    assert len(changes) == 1
    assert changes[0].kind == "change"
    assert changes[0].cut == pytest.approx(60.0, abs=1.0)


def test_find_changes_is_empty_for_steady_sound():
    steady = np.tile([0.5, 0.2, 0.15, 0.1, 0.05], (120, 1))
    assert ss.find_changes(steady) == []


# ---------------------------------------------------------------------------
# Anchors
# ---------------------------------------------------------------------------

def _transcript(*segments):
    return {"segments": [{"start": s, "end": e, "text": t} for s, e, t in segments]}


def test_find_anchors_matches_full_title():
    anchors = ss.find_anchors(
        ["Red House", "Room Full Of Mirrors"],
        _transcript((10, 14, "There's a red house over yonder"), (200, 206, "a room full of mirrors")),
    )
    full = [(a.song_index, a.weight) for a in anchors if a.weight == 1.0]
    assert full == [(0, 1.0), (1, 1.0)]


def test_find_anchors_single_word_must_be_distinctive():
    anchors = ss.find_anchors(
        ["Hey Baby", "Hey Joe", "Foxy Lady"],
        _transcript((5, 8, "hey hey hey"), (50, 52, "you foxy thing")),
    )
    assert [(a.song_index, a.text) for a in anchors] == [(2, "foxy")]


def test_find_anchors_uses_word_timestamps_when_present():
    transcript = {"segments": [{
        "start": 0.0, "end": 30.0, "text": " blah purple haze",
        "words": [
            {"word": " blah", "start": 1.0, "end": 2.0},
            {"word": " purple", "start": 21.0, "end": 22.0},
            {"word": " haze", "start": 22.0, "end": 23.0},
        ],
    }]}
    anchors = ss.find_anchors(["Purple Haze"], transcript)
    assert anchors[0].time == pytest.approx(21.0)


def test_gothenburg_transcript_has_title_anchors():
    titles = ss.parse_setlist(GOTHENBURG / "setlist.txt")
    transcript = ss.load_transcript(GOTHENBURG / "whisper_small.json")
    full = {titles[a.song_index] for a in ss.find_anchors(titles, transcript) if a.weight == 1.0}
    assert {"Message To Love", "Hey Baby", "Foxy Lady", "Red House", "Room Full Of Mirrors"} <= full


def test_announcement_during_break_counts_for_the_next_song():
    brk = ss.Break(start=100.0, end=140.0, depth_db=25.0, quiet_seconds=30.0, cut=137.0, kind="break")
    moved = ss.announce_anchors([ss.Anchor(1, 105.0, 1.0, "title")], [brk])
    assert moved[0].time > brk.cut
    untouched = ss.announce_anchors([ss.Anchor(1, 300.0, 1.0, "title")], [brk])
    assert untouched[0].time == 300.0


# ---------------------------------------------------------------------------
# choose_boundaries
# ---------------------------------------------------------------------------

def _cand(cut, score, kind="break"):
    return ss.Break(start=cut - 2, end=cut + 3, depth_db=20.0, quiet_seconds=5.0, cut=cut, score=score, kind=kind)


def test_choose_boundaries_takes_strongest_breaks_without_anchors():
    cands = [_cand(300, 1.0), _cand(450, 0.3), _cand(600, 0.9)]
    assert ss.choose_boundaries(cands, [], 3, 0.0, 900.0) == [300, 600]


def test_choose_boundaries_anchor_overrules_a_stronger_false_break():
    # A strong pause at 450 sits inside song 2. Without the anchor it would be
    # picked and every later title would slide down one place.
    cands = [_cand(300, 0.8), _cand(450, 1.0), _cand(600, 0.5), _cand(900, 0.9)]
    anchors = [ss.Anchor(1, 350.0, 1.0), ss.Anchor(1, 500.0, 1.0), ss.Anchor(2, 700.0, 1.0)]
    assert ss.choose_boundaries(cands, anchors, 4, 0.0, 1200.0) == [300, 600, 900]


def test_choose_boundaries_respects_minimum_song_length():
    cands = [_cand(300, 1.0), _cand(320, 1.0), _cand(600, 0.2)]
    assert ss.choose_boundaries(cands, [], 3, 0.0, 900.0) == [320, 600] or \
        ss.choose_boundaries(cands, [], 3, 0.0, 900.0) == [300, 600]


def test_choose_boundaries_returns_none_when_too_few_candidates():
    assert ss.choose_boundaries([_cand(300, 1.0)], [], 4, 0.0, 900.0) is None


def test_choose_boundaries_prefers_cut_where_the_key_changes():
    # two "songs" with different pitch content, two equally scored candidates
    song_a = np.tile(np.eye(12)[0], (300, 1))
    song_b = np.tile(np.eye(12)[5], (300, 1))
    chroma = np.vstack([song_a, song_b])
    cands = [_cand(200, 0.2, "change"), _cand(300, 0.2, "change"), _cand(400, 0.2, "change")]
    assert ss.choose_boundaries(cands, [], 2, 0.0, 600.0, chroma=chroma) == [300]


# ---------------------------------------------------------------------------
# show_limits / formatting
# ---------------------------------------------------------------------------

def test_show_limits_trims_quiet_opening_and_closing_applause():
    level = _level((15, -45), (300, -10), (20, -35))
    first, end = ss.show_limits(level, 335.0)
    assert first == pytest.approx(15.0, abs=0.5)
    assert end == pytest.approx(315.0, abs=0.5)


def test_show_limits_defaults_to_whole_file():
    level = _level((300, -10))
    assert ss.show_limits(level, 300.0) == (0.0, 300.0)


def test_format_time_matches_boundaries_file_style():
    assert ss.format_time(17.7) == "0:17.7"
    assert ss.format_time(3958.1) == "65:58.1"


def test_format_boundaries_lists_every_song_and_the_end():
    split = ss.SetlistSplit(titles=["A", "B"], starts=[0.0, 125.5], end=300.0)
    text = ss.format_boundaries(split)
    assert "1   0:00.0    A" in text
    assert "2   2:05.5    B" in text
    assert text.splitlines()[-1].startswith("End 5:00.0")


# ---------------------------------------------------------------------------
# riftkit wiring
# ---------------------------------------------------------------------------

def test_cue_split_stops_last_song_at_end_time(tmp_path):
    audio = tmp_path / "show.mp3"
    audio.touch()
    calls = []
    with patch("riftkit.probe_duration", return_value=1000.0), \
            patch("riftkit.export_segment", side_effect=lambda a, d, s, e: calls.append((s, e))):
        riftkit.split_concert_into_songs(
            audio, tmp_path, song_cues=[(10.0, "A"), (400.0, "B")], end_time=900.0
        )
    assert calls == [(10.0, 400.0), (400.0, 900.0)]


def test_cue_split_without_end_time_is_unchanged(tmp_path):
    audio = tmp_path / "show.mp3"
    audio.touch()
    calls = []
    with patch("riftkit.probe_duration", return_value=1000.0), \
            patch("riftkit.export_segment", side_effect=lambda a, d, s, e: calls.append((s, e))):
        riftkit.split_concert_into_songs(audio, tmp_path, song_cues=[(10.0, "A"), (400.0, "B")])
    assert calls == [(10.0, 400.0), (400.0, 1000.0)]


def test_split_concert_by_setlist_writes_boundaries_and_uses_cue_path(tmp_path):
    audio = tmp_path / "show.mp3"
    audio.touch()
    setlist = tmp_path / "setlist.txt"
    setlist.write_text("1. First\n2. Second\n")
    fake = ss.SetlistSplit(titles=["First", "Second"], starts=[5.0, 200.0], end=390.0)
    calls = []
    with patch("setlist_split.detect_setlist_boundaries", return_value=fake), \
            patch("riftkit.probe_duration", return_value=400.0), \
            patch("riftkit.export_segment", side_effect=lambda a, d, s, e: calls.append((d.name, s, e))):
        split_dir = riftkit.split_concert_by_setlist(audio, tmp_path, setlist)
    assert calls == [("01 - First.mp3", 5.0, 200.0), ("02 - Second.mp3", 200.0, 390.0)]
    assert "2   3:20.0    Second" in (split_dir / "boundaries.txt").read_text()


def test_split_concert_by_setlist_needs_a_setlist(tmp_path):
    audio = tmp_path / "show.mp3"
    audio.touch()
    with pytest.raises(RuntimeError, match="setlist file"):
        riftkit.split_concert_by_setlist(audio, tmp_path, tmp_path / "missing.txt")
