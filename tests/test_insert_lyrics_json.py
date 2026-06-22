from __future__ import annotations

import json
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "lyrics"


def trim(text: str) -> str:
    return (text or "").strip()


def sanitize_lyric_text(text: str) -> str:
    return " ".join(trim(text).split())


def segment_is_terminal(text: str) -> bool:
    return text.endswith((".", "!", "?"))


def normalize_timestamp_entry(entry):
    if not isinstance(entry, dict):
        return None

    text = sanitize_lyric_text(entry.get("text") or entry.get("word") or entry.get("token") or "")
    if not text:
        return None

    start_seconds = entry.get("start", entry.get("begin", entry.get("from")))
    end_seconds = entry.get("end", entry.get("finish", entry.get("to")))

    offsets = entry.get("offsets")
    if isinstance(offsets, dict):
        if offsets.get("from") is not None:
            start_seconds = float(offsets["from"]) / 1000
        if offsets.get("to") is not None:
            end_seconds = float(offsets["to"]) / 1000

    start_seconds = float(start_seconds) if start_seconds is not None else None
    end_seconds = float(end_seconds) if end_seconds is not None else None

    if start_seconds is None:
        return None
    if end_seconds is None or end_seconds <= start_seconds:
        end_seconds = start_seconds + 0.5

    return {"text": text, "start": start_seconds, "finish": end_seconds}


def derive_entries_from_words(words):
    entries = []
    current = None

    def flush_current():
        nonlocal current
        if current and current["text"]:
            entries.append(current)
        current = None

    for word in words:
        normalized = normalize_timestamp_entry(word)
        if not normalized:
            continue

        should_break = False
        if current:
            gap = normalized["start"] - current["finish"]
            if gap > 0.8:
                should_break = True
            elif current["word_count"] >= 10:
                should_break = True
            elif current["char_count"] >= 60:
                should_break = True
            elif segment_is_terminal(current["text"]):
                should_break = True

        if should_break:
            flush_current()

        if current is None:
            current = {
                "text": normalized["text"],
                "start": normalized["start"],
                "finish": normalized["finish"],
                "word_count": 1,
                "char_count": len(normalized["text"]),
            }
        else:
            current["text"] += " " + normalized["text"]
            current["finish"] = normalized["finish"]
            current["word_count"] += 1
            current["char_count"] += 1 + len(normalized["text"])

    flush_current()
    return entries


def extract_entries(transcript):
    if not isinstance(transcript, dict):
        raise AssertionError("Transcript must decode into an object")

    if isinstance(transcript.get("transcription"), list):
        source = transcript["transcription"]
        entries = [normalize_timestamp_entry(entry) for entry in source]
    elif isinstance(transcript.get("segments"), list):
        source = transcript["segments"]
        entries = [normalize_timestamp_entry(entry) for entry in source]
    elif isinstance(transcript.get("words"), list):
        return derive_entries_from_words(transcript["words"])
    else:
        raise AssertionError("Missing supported transcription fields")

    return [entry for entry in entries if entry is not None]


def read_fixture(name: str):
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def test_openai_segments_are_imported_directly():
    transcript = read_fixture("openai_segments_sample.json")

    assert extract_entries(transcript) == [
        {"text": "Foxy Lady", "start": 0.0, "finish": 1.5},
        {"text": "what you want now", "start": 2.0, "finish": 4.2},
    ]


def test_openai_words_are_grouped_into_lyric_lines():
    transcript = read_fixture("openai_words_sample.json")

    assert extract_entries(transcript) == [
        {"text": "you got me baby.", "start": 0.0, "finish": 0.9, "word_count": 4, "char_count": 16},
        {"text": "I want you", "start": 2.0, "finish": 2.4, "word_count": 3, "char_count": 10},
    ]
