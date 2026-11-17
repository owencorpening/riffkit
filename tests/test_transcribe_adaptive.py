from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parent.parent / "lyrics-sync" / "transcribe_adaptive.py"
)
spec = importlib.util.spec_from_file_location("transcribe_adaptive", MODULE_PATH)
ta = importlib.util.module_from_spec(spec)
sys.modules["transcribe_adaptive"] = ta
spec.loader.exec_module(ta)


def make_word(word, probability=0.95, start=0.0, end=0.5):
    return {"word": word, "probability": probability, "start": start, "end": end}


def make_segment(text, words=None, **overrides):
    seg = {
        "id": 0,
        "start": 0.0,
        "end": 2.0,
        "text": text,
        "avg_logprob": -0.2,
        "compression_ratio": 1.4,
        "no_speech_prob": 0.05,
        "temperature": 0.0,
        "words": words if words is not None else [make_word(f" {t}") for t in text.split()],
    }
    seg.update(overrides)
    return seg


# ---------------------------------------------------------------------------
# Suspicion scoring
# ---------------------------------------------------------------------------

def test_clean_segment_has_no_suspicion():
    assert ta.suspicion_reasons(make_segment("Hello Austin")) == []


def test_low_logprob_flags_segment():
    seg = make_segment("mumble", avg_logprob=-1.2)
    assert "low_avg_logprob" in ta.suspicion_reasons(seg)


def test_weak_word_flags_segment():
    words = [make_word(" Hello", 0.95), make_word(" Boston", 0.3)]
    seg = make_segment("Hello Boston", words=words)
    assert "weak_word" in ta.suspicion_reasons(seg)


def test_repetition_and_temperature_flag_segment():
    seg = make_segment("la la la la", compression_ratio=3.0, temperature=0.6)
    reasons = ta.suspicion_reasons(seg)
    assert "high_compression_ratio" in reasons
    assert "temperature_fallback" in reasons


def test_confidence_is_mean_word_probability():
    words = [make_word(" a", 0.8), make_word(" b", 0.6)]
    assert ta.segment_confidence(make_segment("a b", words=words)) == 0.7


def test_merge_suspect_spans_groups_neighbors():
    segments = [
        make_segment("clean", start=0.0, end=2.0),
        make_segment("bad one", start=2.0, end=4.0, avg_logprob=-1.5),
        make_segment("bad two", start=4.3, end=6.0, avg_logprob=-1.5),
        make_segment("clean", start=10.0, end=12.0),
        make_segment("bad far", start=20.0, end=22.0, avg_logprob=-1.5),
    ]
    spans = ta.merge_suspect_spans(segments)
    assert spans == [(2.0, 6.0, [1, 2]), (20.0, 22.0, [4])]


# ---------------------------------------------------------------------------
# Phonetics
# ---------------------------------------------------------------------------

def test_phonetic_keys():
    assert ta.phonetic_key("Boston") == "PSTN"
    assert ta.phonetic_key("Austin") == "ASTN"
    assert ta.phonetic_key("Knight") != ""


def test_boston_austin_are_phonetically_close():
    assert ta.word_similarity("Boston", "Austin") >= ta.SUBSTITUTION_THRESHOLD


def test_unrelated_words_are_not_close():
    assert ta.word_similarity("Hello", "Freedom") < ta.SUBSTITUTION_THRESHOLD


def test_short_words_with_lossy_phonetic_keys_are_not_close():
    # "that" and "to" both collapse to phonetic key "T"; the spelling floor
    # must keep them from being treated as a mishearing.
    assert ta.word_similarity("that", "to") < ta.SUBSTITUTION_THRESHOLD


def test_identical_words_score_one():
    assert ta.word_similarity("hello,", "Hello") == 1.0


# ---------------------------------------------------------------------------
# Reference lyric alignment
# ---------------------------------------------------------------------------

def test_parse_reference_lyrics_drops_section_headers():
    text = "[Verse 1]\nHello Austin\n\n[Chorus]\nsing it loud"
    assert ta.parse_reference_lyrics(text) == ["Hello", "Austin", "sing", "it", "loud"]


def test_reference_substitutes_misheard_word():
    words = [
        make_word(" Hello", start=1.0, end=1.4),
        make_word(" Boston", start=1.5, end=2.0),
    ]
    segments = [make_segment("Hello Boston", words=words, start=1.0, end=2.0)]
    report = ta.apply_reference_lyrics(segments, ["Hello", "Austin"])

    corrected = segments[0]["words"][1]
    assert corrected["word"] == " Austin"
    assert corrected["corrected"] is True
    assert corrected["original"] == "Boston"
    assert corrected["start"] == 1.5  # timestamp preserved
    assert segments[0]["text"] == " Hello Austin"
    assert report.corrections[0]["heard"] == "Boston"
    assert report.corrections[0]["corrected_to"] == "Austin"


def test_reference_leaves_genuine_mismatches_alone():
    words = [make_word(" Goodbye"), make_word(" Austin")]
    segments = [make_segment("Goodbye Austin", words=words)]
    report = ta.apply_reference_lyrics(segments, ["Hello", "Austin"])

    assert segments[0]["words"][0]["word"] == " Goodbye"
    assert not report.corrections
    assert "Goodbye" in report.unmatched_transcript
    assert "Hello" in report.unmatched_reference


def test_reference_reports_missing_words():
    words = [make_word(" Hello")]
    segments = [make_segment("Hello", words=words)]
    report = ta.apply_reference_lyrics(segments, ["Hello", "beautiful", "Austin"])
    assert report.unmatched_reference == ["beautiful", "Austin"]


# ---------------------------------------------------------------------------
# Escalation helpers
# ---------------------------------------------------------------------------

def test_offset_segments_shifts_times_and_tags_model():
    seg = make_segment("hi", words=[make_word(" hi", start=0.2, end=0.6)], start=0.0, end=1.0)
    (out,) = ta.offset_segments([seg], 10.0, "medium")
    assert out["start"] == 10.0
    assert out["end"] == 11.0
    assert out["model"] == "medium"
    assert out["escalated"] is True
    assert out["words"][0]["start"] == 10.2


def test_candidate_score_penalizes_repetition():
    clean = [make_segment("real lyrics", compression_ratio=1.2)]
    loopy = [make_segment("la la la", compression_ratio=3.5)]
    assert ta.candidate_score(clean) > ta.candidate_score(loopy)


def test_candidate_score_empty_is_zero():
    assert ta.candidate_score([]) == 0.0


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------

def test_build_output_is_insertlyrics_compatible():
    words = [make_word(" Hello", start=1.0, end=1.4), make_word(" Austin", start=1.5, end=2.0)]
    segments = [make_segment("Hello Austin", words=words, start=1.0, end=2.0, model="small")]
    doc = ta.build_output(
        Path("vocals.mp3"), segments, [], None, {"base_model": "small", "language": "en"}
    )

    assert doc["schema"] == "riffkit-transcript-v1"
    # InsertLyrics.lua reads transcript.segments[].start/end/text and words[].
    seg = doc["segments"][0]
    assert set(seg) >= {"start", "end", "text", "words", "confidence", "model"}
    word = seg["words"][0]
    assert set(word) >= {"word", "start", "end", "probability"}
    assert doc["text"] == "Hello Austin"


def test_build_output_includes_reference_report():
    report = ta.ReferenceReport(
        corrections=[{"heard": "Boston", "corrected_to": "Austin"}],
        unmatched_reference=["beautiful"],
    )
    doc = ta.build_output(Path("v.mp3"), [], [], report, {})
    assert doc["reference"]["corrections"][0]["corrected_to"] == "Austin"
    assert doc["reference"]["unmatched_reference_words"] == ["beautiful"]


# ---------------------------------------------------------------------------
# faster-whisper backend (stand-in model: no audio, no download)
# ---------------------------------------------------------------------------

import types
from collections import namedtuple

import numpy as np

FakeWord = namedtuple("FakeWord", "start end word probability")
FakeSegment = namedtuple(
    "FakeSegment",
    "id seek start end text tokens avg_logprob compression_ratio "
    "no_speech_prob words temperature",
)

SEGMENT_KEYS = {
    "id", "start", "end", "text", "avg_logprob", "compression_ratio",
    "no_speech_prob", "temperature", "words",
}


def fake_segment(text, start, end, temperature=0.0):
    words = [
        FakeWord(start + i * 0.4, start + i * 0.4 + 0.3, f" {w}", 0.9)
        for i, w in enumerate(text.split())
    ]
    return FakeSegment(1, 0, start, end, f" {text}", [1, 2], -0.2, 1.3, 0.02, words, temperature)


def install_fake_faster_whisper(monkeypatch, segments):
    calls = {"models": [], "transcribe": []}

    class FakeModel:
        def __init__(self, name, device=None, compute_type=None):
            calls["models"].append((name, device, compute_type))

        def transcribe(self, audio, **kwargs):
            calls["transcribe"].append(kwargs)
            return (s for s in segments), object()  # lazy, like the real one

    module = types.SimpleNamespace(
        WhisperModel=FakeModel,
        decode_audio=lambda path, sampling_rate=16000: np.zeros(sampling_rate * 10, dtype=np.float32),
    )
    monkeypatch.setitem(sys.modules, "faster_whisper", module)
    return calls


def test_segment_to_dict_matches_openai_whisper_shape():
    seg = ta.segment_to_dict(fake_segment("purple haze all in my brain", 1.0, 4.0), 3)
    assert set(seg) == SEGMENT_KEYS
    assert seg["id"] == 3
    assert seg["start"] == 1.0 and seg["end"] == 4.0
    assert seg["text"] == " purple haze all in my brain"
    assert seg["avg_logprob"] == -0.2
    assert seg["compression_ratio"] == 1.3
    assert seg["no_speech_prob"] == 0.02
    assert seg["temperature"] == 0.0
    assert len(seg["words"]) == 6
    assert set(seg["words"][0]) == {"word", "start", "end", "probability"}
    assert seg["words"][0]["word"] == " purple"
    assert all(isinstance(v, float) for w in seg["words"] for k, v in w.items() if k != "word")


def test_segment_to_dict_handles_missing_words_and_temperature():
    seg = ta.segment_to_dict(fake_segment("hey", 0.0, 1.0)._replace(words=None, temperature=None), 0)
    assert seg["words"] == []
    assert seg["temperature"] == 0.0


def test_transcribe_returns_same_shape_with_faster_whisper(monkeypatch):
    calls = install_fake_faster_whisper(
        monkeypatch,
        [fake_segment("purple haze all in my brain", 0.5, 3.0),
         fake_segment("lately things just dont seem the same", 3.5, 6.0)],
    )
    transcriber = ta.AdaptiveTranscriber("medium", None, "en")
    segments, log = transcriber.transcribe(Path("vocals.wav"))

    assert log == []
    assert [s["id"] for s in segments] == [0, 1]
    for seg in segments:
        assert set(seg) == SEGMENT_KEYS | {"model", "escalated"}
        assert seg["model"] == "medium" and seg["escalated"] is False

    assert calls["models"] == [("medium", "cpu", "int8")]
    opts = calls["transcribe"][0]
    assert opts["language"] == "en"
    assert opts["word_timestamps"] is True
    assert opts["beam_size"] == 5 and opts["best_of"] == 5
    assert opts["condition_on_previous_text"] is True
    assert opts["initial_prompt"] is None

    # Downstream output is built exactly as before.
    doc = ta.build_output(Path("vocals.wav"), segments, log, None, {"language": "en"})
    assert doc["schema"] == "riffkit-transcript-v1"
    assert len(doc["segments"]) == 2
    assert doc["segments"][0]["words"][0]["word"] == " purple"


def test_models_are_loaded_once_per_name(monkeypatch):
    calls = install_fake_faster_whisper(monkeypatch, [fake_segment("hey joe", 0.0, 1.0)])
    transcriber = ta.AdaptiveTranscriber("small", None, "en")
    transcriber.transcribe(Path("a.wav"))
    transcriber.transcribe(Path("b.wav"))
    assert calls["models"] == [("small", "cpu", "int8")]


def test_escalation_still_splices_with_faster_whisper(monkeypatch):
    # A low-confidence base segment triggers escalation; the stand-in returns
    # the same confident segment for the retry, so the loop runs end to end.
    weak = fake_segment("scuse me while i kiss the sky", 1.0, 4.0)
    weak = weak._replace(
        avg_logprob=-1.5,
        words=[w._replace(probability=0.1) for w in weak.words],
    )
    install_fake_faster_whisper(monkeypatch, [weak])
    transcriber = ta.AdaptiveTranscriber("small", "medium", "en")
    segments, log = transcriber.transcribe(Path("vocals.wav"))
    assert len(log) == 1
    assert log[0]["winner"] in {"base", "escalation"}
    assert [s["id"] for s in segments] == list(range(len(segments)))
