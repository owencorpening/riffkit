#!/usr/bin/env python3
"""Clean a Whisper transcript of a vocal stem before it goes into REAPER.

Whisper, run on an isolated vocal stem, makes three recurring mistakes
(measured on the Winterland 1968 set, Nov 2026):

1. It invents text during instrumental passages ("Thank you." eleven times
   in an instrumental Sunshine Of Your Love).
2. It copies real lines to later times, often as sub-second segments,
   during guitar solos.
3. It merges several sung lines into one 15-30 second segment, which is
   useless for karaoke timing.

Both 1 and 2 land where the vocal stem is silent. On that set every invented
or copied line measured -57 dB or quieter (most near -85 dB), and every real
line, stage talk included, -45 dB or louder. So the cleanup is:

- split long segments into lines at word gaps and sentence ends;
- drop any line whose stretch of the vocal stem is near silent;
- drop empty and zero-length lines;
- move each line's start to where the vocal stem goes from quiet to loud,
  if that is within 0.75 s (Whisper's starts are often a few tenths off).

Text is never rewritten; only whole lines are split or dropped.

Usage:
    .venv/bin/python lyrics-sync/clean_transcript.py transcript.json vocals.wav \
        --output transcript_clean.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
FRAME_SECONDS = 0.05

# A line is kept only if the loudest 10% of its frames reach this level.
SILENCE_FLOOR_DB = -50.0
# Segments longer than this are split into lines.
MAX_LINE_SECONDS = 8.0
# A pause between words at least this long starts a new line.
LINE_GAP_SECONDS = 0.5
# Lines shorter than this cannot be shown and are dropped.
MIN_LINE_SECONDS = 0.05

# Line starts snap to the vocal stem crossing this level ...
ONSET_THRESHOLD_DB = -40.0
# ... if the crossing is within this many seconds of Whisper's start.
ONSET_SEARCH_SECONDS = 0.75
# A crossing counts only if the stem then reaches within ONSET_NEAR_PEAK_DB of
# the line's own level inside ONSET_RISE_SECONDS. Guitar bleed in the vocal
# stem crosses -40 dB too, but stays well below the singing (Foxey Lady,
# "I see you": bleed at -26..-38 dB, voice at -16 dB).
ONSET_RISE_SECONDS = 0.3
ONSET_NEAR_PEAK_DB = 6.0

TERMINAL_PUNCTUATION =(".", "!", "?")


def frame_levels_db(samples: np.ndarray, sample_rate: int = SAMPLE_RATE,
                    frame_seconds: float = FRAME_SECONDS) -> np.ndarray:
    """RMS level in dB for each consecutive frame of a mono signal."""
    size = max(1, int(round(sample_rate * frame_seconds)))
    usable = len(samples) // size * size
    if usable == 0:
        return np.full(1, -120.0)
    frames = np.asarray(samples[:usable], dtype=np.float64).reshape(-1, size)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    return 20 * np.log10(rms + 1e-9)


def line_level_db(levels: np.ndarray, start: float, end: float,
                  frame_seconds: float = FRAME_SECONDS) -> float:
    """90th-percentile frame level over [start, end] (at least one frame)."""
    first = max(0, int(start / frame_seconds))
    last = max(first + 1, int(np.ceil(end / frame_seconds)))
    window = levels[first:last]
    if window.size == 0:
        return -120.0
    return float(np.percentile(window, 90))


def _segment_from_words(template: dict, words: list[dict]) -> dict:
    seg = dict(template)
    seg["words"] = words
    seg["start"] = float(words[0]["start"])
    seg["end"] = float(words[-1]["end"])
    seg["text"] = "".join(w["word"] for w in words)
    return seg


def split_long_segment(seg: dict, max_seconds: float = MAX_LINE_SECONDS,
                       gap_seconds: float = LINE_GAP_SECONDS) -> list[dict]:
    """Split a segment longer than max_seconds at word gaps and sentence ends.

    Segments without word timestamps cannot be split and are returned as is.
    """
    words = seg.get("words") or []
    if float(seg["end"]) - float(seg["start"]) <= max_seconds or len(words) < 2:
        return [seg]

    lines: list[list[dict]] = [[words[0]]]
    for prev, word in zip(words, words[1:]):
        gap = float(word["start"]) - float(prev["end"])
        if gap >= gap_seconds or prev["word"].strip().endswith(TERMINAL_PUNCTUATION):
            lines.append([word])
        else:
            lines[-1].append(word)
    return [_segment_from_words(seg, line) for line in lines]


def snap_starts_to_onsets(segments: list[dict], levels: np.ndarray, *,
                          threshold_db: float = ONSET_THRESHOLD_DB,
                          search_seconds: float = ONSET_SEARCH_SECONDS,
                          frame_seconds: float = FRAME_SECONDS) -> int:
    """Move each line's start to where the vocal stem goes from quiet to loud.

    Whisper's line starts are often a few tenths of a second early or late.
    The nearest quiet-to-loud crossing within ``search_seconds`` of the start
    that leads into the line's full level (not quieter bleed)
    (and not before the previous line ends) becomes the new start. Lines with
    no such crossing (voice already sounding, or silence) are left alone.
    Modifies segments in place; returns how many lines moved.
    """
    moved = 0
    prev_end = 0.0
    for seg in segments:
        start, end = float(seg["start"]), float(seg["end"])
        lo = max(prev_end, start - search_seconds, 0.0)
        hi = min(start + search_seconds, end - MIN_LINE_SECONDS)
        first, last = int(np.ceil(lo / frame_seconds)), int(hi / frame_seconds)
        target = line_level_db(levels, start, end, frame_seconds) - ONSET_NEAR_PEAK_DB
        rise = int(ONSET_RISE_SECONDS / frame_seconds) + 1
        best = None
        for j in range(max(first, 1), min(last, len(levels) - 1) + 1):
            if (levels[j] > threshold_db >= levels[j - 1]
                    and levels[j:j + rise].max() >= target):
                t = j * frame_seconds
                if best is None or abs(t - start) < abs(best - start):
                    best = t
        if best is not None and abs(best - start) >= frame_seconds:
            seg["start"] = best
            words = seg.get("words") or []
            if words:
                words[0] = {**words[0], "start": min(best, float(words[0]["end"]))}
            moved += 1
        prev_end = float(seg["end"])
    return moved


def clean_segments(segments: list[dict], levels: np.ndarray, *,
                   floor_db: float = SILENCE_FLOOR_DB,
                   max_seconds: float = MAX_LINE_SECONDS,
                   gap_seconds: float = LINE_GAP_SECONDS) -> tuple[list[dict], dict]:
    """Return (cleaned segments, report). Input segments are not modified."""
    report = {"split": 0, "dropped_empty": 0, "dropped_silent": [], "floor_db": floor_db}
    kept: list[dict] = []
    for seg in segments:
        pieces = split_long_segment(dict(seg), max_seconds, gap_seconds)
        if len(pieces) > 1:
            report["split"] += 1
        for piece in pieces:
            text = piece.get("text", "").strip()
            start, end = float(piece["start"]), float(piece["end"])
            if not text or end - start < MIN_LINE_SECONDS:
                report["dropped_empty"] += 1
                continue
            level = line_level_db(levels, start, end)
            if level < floor_db:
                report["dropped_silent"].append(
                    {"start": round(start, 2), "end": round(end, 2),
                     "level_db": round(level, 1), "text": text}
                )
                continue
            kept.append(piece)
    report["starts_moved"] = snap_starts_to_onsets(kept, levels)
    for i, seg in enumerate(kept):
        seg["id"] = i
    return kept, report


def load_mono(path: Path, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Decode any audio file to mono float32 at sample_rate with ffmpeg."""
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
         "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "-"],
        capture_output=True, check=True,
    )
    return np.frombuffer(result.stdout, dtype=np.float32)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("transcript", help="Whisper-style JSON with a 'segments' list")
    parser.add_argument("vocals", help="The vocal stem the transcript came from")
    parser.add_argument("--output", "-o",
                        help="Output JSON (default: <transcript>_clean.json)")
    parser.add_argument("--floor-db", type=float, default=SILENCE_FLOOR_DB)
    args = parser.parse_args()

    transcript_path = Path(args.transcript).expanduser()
    vocals_path = Path(args.vocals).expanduser()
    for p in (transcript_path, vocals_path):
        if not p.exists():
            print(f"error: file not found: {p}", file=sys.stderr)
            return 1

    doc = json.loads(transcript_path.read_text(encoding="utf-8"))
    levels = frame_levels_db(load_mono(vocals_path))
    segments, report = clean_segments(doc["segments"], levels, floor_db=args.floor_db)
    doc["segments"] = segments
    doc["text"] = "".join(s["text"] for s in segments).strip()
    doc["cleanup"] = report

    out = Path(args.output) if args.output else transcript_path.with_name(
        transcript_path.stem + "_clean.json")
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[clean] {len(segments)} lines kept, {report['split']} split, "
          f"{len(report['dropped_silent'])} silent and {report['dropped_empty']} empty "
          f"dropped, {report['starts_moved']} starts moved "
          f"-> {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
