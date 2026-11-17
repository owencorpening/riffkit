from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

MODULE_PATH = (
    Path(__file__).resolve().parent.parent / "lyrics-sync" / "clean_transcript.py"
)
spec = importlib.util.spec_from_file_location("clean_transcript", MODULE_PATH)
ct = importlib.util.module_from_spec(spec)
sys.modules["clean_transcript"] = ct
spec.loader.exec_module(ct)

SR = ct.SAMPLE_RATE


def stem(duration, loud_spans):
    """Silent signal with a sine tone (about -20 dB) over each (start, end) span."""
    audio = np.zeros(int(duration * SR), dtype=np.float32)
    for start, end in loud_spans:
        t = np.arange(int(start * SR), int(end * SR))
        audio[t] = 0.14 * np.sin(2 * np.pi * 220 * t / SR)
    return audio


def word(text, start, end):
    return {"word": text, "start": start, "end": end, "probability": 0.9}


def seg(text, start, end, words=None):
    return {"text": text, "start": start, "end": end, "words": words or [],
            "avg_logprob": -0.3}


def test_frame_levels_separate_tone_from_silence():
    levels = ct.frame_levels_db(stem(2.0, [(0.0, 1.0)]))
    assert len(levels) == 40
    assert levels[:20].min() > -25
    assert levels[20:].max() < -100


def test_line_over_silent_stem_is_dropped_and_sung_line_kept():
    levels = ct.frame_levels_db(stem(10.0, [(1.0, 3.0)]))
    segments = [seg(" Help me, baby.", 1.0, 3.0), seg(" Thank you.", 6.0, 7.5)]
    kept, report = ct.clean_segments(segments, levels)
    assert [s["text"] for s in kept] == [" Help me, baby."]
    assert [d["text"] for d in report["dropped_silent"]] == ["Thank you."]


def test_repeated_chorus_over_vocals_is_kept():
    levels = ct.frame_levels_db(stem(10.0, [(1.0, 2.5), (4.0, 5.5)]))
    segments = [seg(" Let me stand, baby.", 1.0, 2.5), seg(" Let me stand, baby.", 4.0, 5.5)]
    kept, _ = ct.clean_segments(segments, levels)
    assert len(kept) == 2


def test_empty_and_zero_length_segments_are_dropped():
    levels = ct.frame_levels_db(stem(5.0, [(0.0, 5.0)]))
    segments = [seg("", 1.0, 2.0), seg(" Hey.", 3.0, 3.0), seg(" Yeah.", 3.5, 4.0)]
    kept, report = ct.clean_segments(segments, levels)
    assert [s["text"] for s in kept] == [" Yeah."]
    assert report["dropped_empty"] == 2


def test_long_segment_splits_at_sentence_end_and_word_gap():
    words = [
        word(" I", 0.0, 0.3), word(" want", 0.3, 0.6), word(" you.", 0.6, 1.0),
        word(" Why", 1.1, 1.4), word(" not", 1.4, 1.8),
        word(" come", 5.0, 5.5), word(" home", 5.5, 9.5),
    ]
    pieces = ct.split_long_segment(seg(" I want you. Why not come home", 0.0, 9.5, words))
    assert [p["text"] for p in pieces] == [" I want you.", " Why not", " come home"]
    assert (pieces[1]["start"], pieces[1]["end"]) == (1.1, 1.8)


def test_short_segment_is_not_split():
    words = [word(" I", 0.0, 0.3), word(" want", 2.0, 2.3)]
    assert len(ct.split_long_segment(seg(" I want", 0.0, 2.3, words))) == 1


def test_split_pieces_are_gated_separately():
    # A stretched copy: the first words are sung, the rest lands in a solo.
    levels = ct.frame_levels_db(stem(30.0, [(0.0, 2.0)]))
    words = [word(" I", 0.0, 0.5), word(" feel", 0.5, 1.5),
             word(" I", 10.0, 10.5), word(" gotta", 10.5, 20.0)]
    kept, report = ct.clean_segments([seg(" I feel I gotta", 0.0, 20.0, words)], levels)
    assert [s["text"] for s in kept] == [" I feel"]
    assert report["split"] == 1
    assert [s["id"] for s in kept] == [0]


def test_input_segments_are_not_modified():
    levels = ct.frame_levels_db(stem(30.0, [(0.0, 30.0)]))
    words = [word(" a.", 0.0, 1.0), word(" b", 9.0, 10.0)]
    original = seg(" a. b", 0.0, 10.0, words)
    ct.clean_segments([original], levels)
    assert original["text"] == " a. b" and "id" not in original


def test_early_line_start_moves_to_voice_onset():
    levels = ct.frame_levels_db(stem(10.0, [(3.5, 5.0)]))
    segs = [seg(" late voice", 3.0, 5.0, [word(" late", 3.0, 4.0), word(" voice", 4.0, 5.0)])]
    assert ct.snap_starts_to_onsets(segs, levels) == 1
    assert abs(segs[0]["start"] - 3.5) < 0.06
    assert segs[0]["words"][0]["start"] == segs[0]["start"]


def test_late_line_start_moves_back_to_voice_onset():
    levels = ct.frame_levels_db(stem(10.0, [(2.6, 5.0)]))
    segs = [seg(" early voice", 3.0, 5.0)]
    ct.snap_starts_to_onsets(segs, levels)
    assert abs(segs[0]["start"] - 2.6) < 0.06


def test_start_does_not_move_into_previous_line_or_beyond_search():
    levels = ct.frame_levels_db(stem(10.0, [(1.0, 2.0), (2.2, 4.0), (6.0, 7.0)]))
    segs = [seg(" one", 1.0, 2.5), seg(" two", 2.7, 4.0), seg(" far", 8.0, 9.0)]
    ct.snap_starts_to_onsets(segs, levels)
    assert segs[1]["start"] == 2.7   # onset at 2.2 is inside the previous line
    assert segs[2]["start"] == 8.0   # onset at 6.0 is more than 0.75 s away
