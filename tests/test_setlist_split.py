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
    entries = ss.parse_setlist(GOTHENBURG / "setlist.txt")
    songs = [t for t in entries if not ss.is_skip_entry(t)]
    assert len(songs) == 13
    assert songs[0] == "Spanish Castle Magic"
    assert songs[4] == "Hey Baby"
    assert songs[-1] == "Voodoo Child (Slight Return)"
    # two solos are marked as skip entries: before song 1 and before Hey Baby
    assert entries[0] == "(solo)"
    assert entries[entries.index("Hey Baby") - 1] == "(solo)"


def test_parse_setlist_keeps_skip_entries_in_place(tmp_path):
    f = tmp_path / "setlist.txt"
    f.write_text("1. First\n(drum solo)\n2. Second\n- (jam)\n3. Third (Reprise)\n")
    assert ss.parse_setlist(f) == ["First", "(drum solo)", "Second", "(jam)", "Third (Reprise)"]


def test_is_skip_entry_only_when_wholly_in_parentheses():
    assert ss.is_skip_entry("(solo)")
    assert not ss.is_skip_entry("Voodoo Child (Slight Return)")


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
    assert breaks[0].cut == pytest.approx(103.5, abs=0.5)   # 4.5 s before the band is back
    assert breaks[0].stop() == pytest.approx(100.0, abs=0.5)  # previous song stops where the break begins


def test_find_breaks_merges_dips_separated_by_short_noise():
    # applause burst (4 s, not full volume) in the middle of one break
    level = _level((100, -10), (5, -35), (4, -16), (5, -40), (100, -10))
    breaks = [b for b in ss.find_breaks(level) if b.kind == "break"]
    assert len(breaks) == 1
    assert breaks[0].cut == pytest.approx(109.5, abs=0.6)   # counted back from the deeper, later dip
    assert breaks[0].stop() == pytest.approx(100.0, abs=0.5)


def test_find_breaks_treats_short_full_volume_burst_as_previous_songs_ending():
    # song ... pause ... 8 s final flourish at full volume ... short dip ... next song
    level = _level((100, -10), (4, -40), (8, -10), (1.5, -30), (100, -10))
    breaks = [b for b in ss.find_breaks(level) if b.kind == "break"]
    assert len(breaks) == 1
    assert 104.0 <= breaks[0].cut <= 113.5                  # after the first pause, not at 100
    assert breaks[0].cut == pytest.approx(109.0, abs=0.6)
    assert breaks[0].stop() == pytest.approx(100.0, abs=0.5)


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


def test_choose_boundaries_allows_short_skip_entries():
    # song, 30 s solo, song: the solo is shorter than a song is allowed to be
    cands = [_cand(300, 1.0), _cand(330, 1.0)]
    assert ss.choose_boundaries(cands, [], 3, 0.0, 900.0) is None
    assert ss.choose_boundaries(cands, [], 3, 0.0, 900.0, min_lengths=[60, 20, 60]) == [300, 330]


def test_split_from_features_gives_each_song_its_own_end():
    # two songs with a 10 s break between them and applause at the end
    level = _level((200, -10), (10, -40), (200, -10), (10, -40))
    chroma = np.tile(np.eye(12)[0], (420, 1))
    shares = np.tile([0.5, 0.2, 0.15, 0.1, 0.05], (420, 1))
    split = ss.split_from_features(["One", "Two"], level, chroma, shares, 420.0)
    (s1, e1, _), (s2, e2, _) = split.segments()
    assert e1 == pytest.approx(200.0, abs=0.5)      # stops where the break begins
    assert s2 == pytest.approx(205.5, abs=0.5)      # starts 4.5 s before the band is back
    assert e2 == pytest.approx(410.0, abs=0.5)
    assert split.checks == [[], []]


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
    split = ss.SetlistSplit(
        titles=["A", "(solo)", "B"], starts=[0.0, 120.0, 150.5], ends=[118.0, 150.5, 300.0],
        checks=[[], ["start: no pause here"], ["start: no pause here"]],
    )
    lines = ss.format_boundaries(split).splitlines()
    assert lines[1].split() == ["1", "0:00.0", "1:58.0", "ok", "A"]
    assert lines[2].split() == ["-", "2:00.0", "2:30.5", "CHECK", "(solo)"]
    assert lines[3].split() == ["2", "2:30.5", "5:00.0", "CHECK", "B"]
    assert "Listen to these:" in lines


def test_segments_leave_out_skip_entries():
    split = ss.SetlistSplit(
        titles=["A", "(solo)", "B"], starts=[0.0, 120.0, 150.5], ends=[118.0, 150.5, 300.0],
    )
    assert split.segments() == [(0.0, 118.0, "A"), (150.5, 300.0, "B")]


def test_read_boundaries_file_round_trips_printed_list(tmp_path):
    split = ss.SetlistSplit(
        titles=["A", "(solo)", "B (Live)"], starts=[0.0, 120.0, 150.5], ends=[118.0, 150.5, 3958.1],
        checks=[[], [], ["start: no pause here"]],
    )
    f = tmp_path / "boundaries.txt"
    f.write_text(ss.format_boundaries(split) + "\n")
    assert ss.read_boundaries_file(f) == [(0.0, 118.0, "A"), (150.5, 3958.1, "B (Live)")]


def test_read_boundaries_file_reads_hand_marked_answer_key():
    segments = ss.read_boundaries_file(GOTHENBURG / "boundaries.txt")
    assert len(segments) == 13
    assert segments[0][2] == "Spanish Castle Magic"
    assert segments[-1][2] == "Voodoo Child (Slight Return)"
    assert all(end > start for start, end, _ in segments)


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
    assert "2   3:20.0    6:30.0    ok     Second" in (split_dir / "boundaries.txt").read_text()


def test_song_segments_are_exported_as_given(tmp_path):
    audio = tmp_path / "show.mp3"
    audio.touch()
    calls = []
    with patch("riftkit.probe_duration", return_value=1000.0), \
            patch("riftkit.export_segment", side_effect=lambda a, d, s, e: calls.append((d.name, s, e))):
        riftkit.split_concert_into_songs(
            audio, tmp_path, song_segments=[(10.0, 380.0, "A"), (400.0, 900.0, "B")]
        )
    assert calls == [("01 - A.mp3", 10.0, 380.0), ("02 - B.mp3", 400.0, 900.0)]


def test_split_concert_by_boundaries_runs_no_detection(tmp_path):
    audio = tmp_path / "show.mp3"
    audio.touch()
    boundaries = tmp_path / "boundaries.txt"
    boundaries.write_text(
        "#   Start     End       Check  Song\n"
        "-   0:05.0    1:00.0    CHECK  (solo)\n"
        "1   1:00.0    3:10.0    CHECK  First\n"
        "2   3:20.0    6:30.0    ok     Second\n"
    )
    calls = []
    with patch("setlist_split.detect_setlist_boundaries", side_effect=AssertionError("detection ran")), \
            patch("riftkit.probe_duration", return_value=400.0), \
            patch("riftkit.export_segment", side_effect=lambda a, d, s, e: calls.append((d.name, s, e))):
        riftkit.split_concert_by_boundaries(audio, tmp_path, boundaries)
    assert calls == [("01 - First.mp3", 60.0, 190.0), ("02 - Second.mp3", 200.0, 390.0)]


def test_split_concert_by_setlist_needs_a_setlist(tmp_path):
    audio = tmp_path / "show.mp3"
    audio.touch()
    with pytest.raises(RuntimeError, match="setlist file"):
        riftkit.split_concert_by_setlist(audio, tmp_path, tmp_path / "missing.txt")


# ---------------------------------------------------------------------------
# Beat
# ---------------------------------------------------------------------------

def test_beat_strength_is_high_for_steady_clicks_and_low_for_noise():
    rate = ss.ANALYSIS_SAMPLE_RATE
    rng = np.random.default_rng(0)
    noise = (rng.standard_normal(rate * 20) * 0.1).astype(np.float32)
    clicks = np.zeros(rate * 20, dtype=np.float32)
    for beat in np.arange(0, 20, 0.5):               # 120 beats per minute
        at = int(beat * rate)
        clicks[at:at + 200] = rng.standard_normal(200) * 0.8
    strength = ss.beat_strength(np.concatenate([noise, clicks]))
    assert len(strength) == 40
    assert strength[25:35].mean() > 0.5
    assert strength[5:15].mean() < 0.25


def test_find_beat_starts_marks_where_a_steady_beat_sets_in():
    free = np.full(120, 0.1)
    steady = np.full(120, 0.4)
    starts = ss.find_beat_starts(np.concatenate([free, steady]))
    assert [b.kind for b in starts] == ["beat"]
    assert starts[0].cut == pytest.approx(120.0, abs=1.0)


def test_find_beat_starts_ignores_a_short_break_in_the_beat():
    strength = np.full(400, 0.4)
    strength[200:210] = 0.1                           # a ten second drum-less passage
    assert ss.find_beat_starts(strength) == []
