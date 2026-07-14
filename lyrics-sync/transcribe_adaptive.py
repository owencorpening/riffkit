#!/usr/bin/env python3
"""Adaptive vocal transcription with per-segment escalation and lyric disambiguation.

Pipeline (see docs/session1-transcription-spec.md):

1. Base pass: transcribe the whole vocal stem with a fast Whisper model,
   word timestamps on.
2. Score every segment for suspicion (low log-prob, weak words, repetition,
   temperature fallback, no-speech leakage).
3. Escalate suspicious spans: re-run just those audio slices through a
   larger model with beam search and neighboring-lyric context, then keep
   whichever candidate scores better.
4. If a reference lyric sheet is provided, align the transcript against it
   and substitute acoustically-close mismatches ("Boston" -> "Austin"),
   keeping the audio-derived timestamps.
5. Emit riffkit-transcript-v1 JSON: Whisper-compatible `segments`/`words`
   (InsertLyrics.lua reads it unchanged) plus per-segment provenance.

Usage:
    .venv/bin/python lyrics-sync/transcribe_adaptive.py vocals.mp3 \
        --output vocals.json \
        --base-model small --escalation-model medium \
        --lyrics reference_lyrics.txt

Only the base/escalation Whisper models are loaded lazily, so scoring,
phonetics, and alignment stay importable without torch downloads (tests
rely on this).
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SAMPLE_RATE = 16000

# Suspicion thresholds, tuned against Whisper's own fallback heuristics.
LOGPROB_SUSPECT = -0.8
COMPRESSION_RATIO_SUSPECT = 2.4
NO_SPEECH_SUSPECT = 0.6
WORD_PROB_FLOOR = 0.4
MEAN_WORD_PROB_FLOOR = 0.6
TEMPERATURE_SUSPECT = 0.2

# Padding (seconds) around a suspicious span when re-slicing audio.
SPAN_PAD = 0.35
# Merge suspicious segments closer than this into one escalation span.
SPAN_MERGE_GAP = 0.75

# Minimum combined orthographic+phonetic similarity for a reference-sheet
# substitution to be considered "the same word misheard".
SUBSTITUTION_THRESHOLD = 0.55
# Phonetic keys are lossy on short words ("that" and "to" both key to "T"),
# so a spelling-similarity floor is required as well ("Boston"/"Austin" is 0.5).
ORTHO_FLOOR = 0.4


# ---------------------------------------------------------------------------
# Segment scoring
# ---------------------------------------------------------------------------

def word_probabilities(segment: dict) -> list[float]:
    return [
        float(w["probability"])
        for w in segment.get("words") or []
        if w.get("probability") is not None
    ]


def segment_confidence(segment: dict) -> float:
    """Mean word probability, falling back to exp(avg_logprob)."""
    probs = word_probabilities(segment)
    if probs:
        return sum(probs) / len(probs)
    avg_logprob = segment.get("avg_logprob")
    if avg_logprob is not None:
        return min(1.0, 2.718281828 ** float(avg_logprob))
    return 0.0


def suspicion_reasons(segment: dict) -> list[str]:
    """Why a segment should be escalated; empty list means it looks clean."""
    reasons = []
    if float(segment.get("avg_logprob", 0.0)) < LOGPROB_SUSPECT:
        reasons.append("low_avg_logprob")
    if float(segment.get("compression_ratio", 0.0)) > COMPRESSION_RATIO_SUSPECT:
        reasons.append("high_compression_ratio")
    if float(segment.get("no_speech_prob", 0.0)) > NO_SPEECH_SUSPECT:
        reasons.append("high_no_speech_prob")
    if float(segment.get("temperature", 0.0)) > TEMPERATURE_SUSPECT:
        reasons.append("temperature_fallback")
    probs = word_probabilities(segment)
    if probs:
        if min(probs) < WORD_PROB_FLOOR:
            reasons.append("weak_word")
        if sum(probs) / len(probs) < MEAN_WORD_PROB_FLOOR:
            reasons.append("low_mean_word_prob")
    return reasons


def merge_suspect_spans(segments: list[dict]) -> list[tuple[float, float, list[int]]]:
    """Group suspicious segments into (start, end, segment_indexes) spans.

    Adjacent suspicious segments separated by less than SPAN_MERGE_GAP are
    escalated together so the bigger model gets a coherent phrase, not a
    word fragment.
    """
    spans: list[tuple[float, float, list[int]]] = []
    for idx, seg in enumerate(segments):
        if not suspicion_reasons(seg):
            continue
        start, end = float(seg["start"]), float(seg["end"])
        if spans and start - spans[-1][1] < SPAN_MERGE_GAP:
            prev_start, prev_end, idxs = spans[-1]
            spans[-1] = (prev_start, max(prev_end, end), idxs + [idx])
        else:
            spans.append((start, end, [idx]))
    return spans


# ---------------------------------------------------------------------------
# Phonetic similarity (Boston vs. Austin)
# ---------------------------------------------------------------------------

_PHONE_MAP = {
    "b": "P", "p": "P",
    "f": "F", "v": "F",
    "c": "K", "k": "K", "q": "K", "g": "K", "j": "K",
    "s": "S", "z": "S", "x": "S",
    "d": "T", "t": "T",
    "m": "N", "n": "N",
    "l": "L",
    "r": "R",
}

_VOWELS = set("aeiou")


def normalize_word(word: str) -> str:
    return re.sub(r"[^a-z']", "", word.lower().strip())


def phonetic_key(word: str) -> str:
    """Compact metaphone-ish key: 'boston' -> 'PSTN', 'austin' -> 'ASTN'."""
    w = normalize_word(word).replace("'", "")
    if not w:
        return ""
    key = []
    for i, ch in enumerate(w):
        if ch in _VOWELS:
            if i == 0:
                key.append("A")
            continue
        code = _PHONE_MAP.get(ch)
        if code and (not key or key[-1] != code):
            key.append(code)
    return "".join(key)


def word_similarity(a: str, b: str) -> float:
    """Blend of spelling and phonetic-key similarity in [0, 1]."""
    na, nb = normalize_word(a), normalize_word(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ortho = difflib.SequenceMatcher(None, na, nb).ratio()
    if ortho < ORTHO_FLOOR:
        return ortho
    phon = difflib.SequenceMatcher(None, phonetic_key(na), phonetic_key(nb)).ratio()
    return 0.5 * ortho + 0.5 * phon


# ---------------------------------------------------------------------------
# Reference lyric sheet alignment
# ---------------------------------------------------------------------------

@dataclass
class ReferenceReport:
    corrections: list[dict] = field(default_factory=list)
    unmatched_reference: list[str] = field(default_factory=list)
    unmatched_transcript: list[str] = field(default_factory=list)


def parse_reference_lyrics(text: str) -> list[str]:
    """Reference sheet -> word list. Section headers like [Chorus] are dropped."""
    words = []
    for line in text.splitlines():
        line = re.sub(r"\[[^\]]*\]", " ", line)
        for token in line.split():
            if normalize_word(token):
                words.append(token)
    return words


def _pair_replace_block(trans_block: list[str], ref_block: list[str]) -> list[tuple[int, int]]:
    """Pair up words inside a difflib 'replace' block by phonetic key."""
    matcher = difflib.SequenceMatcher(
        None,
        [phonetic_key(w) for w in trans_block],
        [phonetic_key(w) for w in ref_block],
    )
    pairs = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            pairs.extend((i1 + k, j1 + k) for k in range(i2 - i1))
        elif op == "replace":
            for k in range(min(i2 - i1, j2 - j1)):
                pairs.append((i1 + k, j1 + k))
    if not pairs and len(trans_block) == len(ref_block):
        pairs = list(enumerate(range(len(ref_block))))
    return pairs


def apply_reference_lyrics(segments: list[dict], reference_words: list[str]) -> ReferenceReport:
    """Align flat transcript words to the reference sheet; substitute close mismatches.

    Mutates `segments` in place: corrected words get the reference spelling,
    keep their timestamps, and gain `corrected: True` plus the original text.
    """
    flat: list[tuple[dict, dict]] = [
        (seg, w) for seg in segments for w in seg.get("words") or []
    ]
    trans_norm = [normalize_word(w["word"]) for _, w in flat]
    ref_norm = [normalize_word(w) for w in reference_words]

    report = ReferenceReport()
    matcher = difflib.SequenceMatcher(None, trans_norm, ref_norm, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        if op in ("replace",):
            trans_block = [flat[i][1]["word"] for i in range(i1, i2)]
            ref_block = reference_words[j1:j2]
            paired_t, paired_r = set(), set()
            for ti, rj in _pair_replace_block(trans_block, ref_block):
                t_word = flat[i1 + ti][1]
                ref_word = ref_block[rj]
                score = word_similarity(t_word["word"], ref_word)
                if score >= SUBSTITUTION_THRESHOLD:
                    original = t_word["word"]
                    t_word["original"] = original.strip()
                    t_word["word"] = (" " if original.startswith(" ") else "") + ref_word
                    t_word["corrected"] = True
                    report.corrections.append(
                        {
                            "heard": original.strip(),
                            "corrected_to": ref_word,
                            "similarity": round(score, 3),
                            "start": t_word.get("start"),
                        }
                    )
                    paired_t.add(i1 + ti)
                    paired_r.add(j1 + rj)
            report.unmatched_transcript.extend(
                flat[i][1]["word"].strip() for i in range(i1, i2) if i not in paired_t
            )
            report.unmatched_reference.extend(
                reference_words[j] for j in range(j1, j2) if j not in paired_r
            )
        elif op == "delete":
            report.unmatched_transcript.extend(
                flat[i][1]["word"].strip() for i in range(i1, i2)
            )
        elif op == "insert":
            report.unmatched_reference.extend(reference_words[j1:j2])

    for seg in segments:
        if any(w.get("corrected") for w in seg.get("words") or []):
            seg["text"] = "".join(w["word"] for w in seg["words"])
    return report


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------

def candidate_score(segments: list[dict]) -> float:
    """Score a candidate transcription of a slice: mean word prob, repetition-penalized."""
    if not segments:
        return 0.0
    probs = [p for seg in segments for p in word_probabilities(seg)]
    if not probs:
        return 0.0
    score = sum(probs) / len(probs)
    worst_compression = max(float(s.get("compression_ratio", 0.0)) for s in segments)
    if worst_compression > COMPRESSION_RATIO_SUSPECT:
        score *= 0.5
    return score


def offset_segments(segments: list[dict], offset: float, model_name: str) -> list[dict]:
    """Shift slice-relative timestamps back into track time and tag provenance."""
    out = []
    for seg in segments:
        seg = dict(seg)
        seg["start"] = float(seg["start"]) + offset
        seg["end"] = float(seg["end"]) + offset
        seg["model"] = model_name
        seg["escalated"] = True
        seg["words"] = [
            {**w, "start": float(w["start"]) + offset, "end": float(w["end"]) + offset}
            for w in seg.get("words") or []
        ]
        out.append(seg)
    return out


class AdaptiveTranscriber:
    """Owns lazy model loading + the escalation loop. Kept out of module scope
    so importing this file never touches whisper/torch."""

    def __init__(self, base_model: str, escalation_model: str | None, language: str):
        import whisper  # deferred: heavy import

        self._whisper = whisper
        self.base_model_name = base_model
        self.escalation_model_name = escalation_model
        self.language = language
        self._models: dict[str, object] = {}

    def _model(self, name: str):
        if name not in self._models:
            print(f"[transcribe] loading model: {name}", file=sys.stderr)
            self._models[name] = self._whisper.load_model(name)
        return self._models[name]

    def _run(self, model_name: str, audio, initial_prompt: str | None = None) -> dict:
        return self._model(model_name).transcribe(
            audio,
            language=self.language,
            word_timestamps=True,
            beam_size=5,
            best_of=5,
            condition_on_previous_text=True,
            initial_prompt=initial_prompt,
            verbose=None,
        )

    def transcribe(self, audio_path: Path) -> tuple[list[dict], list[dict]]:
        """Returns (segments, escalation_log)."""
        audio = self._whisper.load_audio(str(audio_path))

        print(f"[transcribe] base pass ({self.base_model_name})…", file=sys.stderr)
        result = self._run(self.base_model_name, audio)
        segments = [dict(s) for s in result["segments"]]
        for seg in segments:
            seg["model"] = self.base_model_name
            seg["escalated"] = False

        escalation_log: list[dict] = []
        if not self.escalation_model_name:
            return segments, escalation_log

        spans = merge_suspect_spans(segments)
        if spans:
            print(
                f"[transcribe] escalating {len(spans)} span(s) to "
                f"{self.escalation_model_name}…",
                file=sys.stderr,
            )
        duration = len(audio) / SAMPLE_RATE

        # Process spans back-to-front so index-based splicing stays valid.
        for start, end, idxs in reversed(spans):
            slice_start = max(0.0, start - SPAN_PAD)
            slice_end = min(duration, end + SPAN_PAD)
            audio_slice = audio[int(slice_start * SAMPLE_RATE):int(slice_end * SAMPLE_RATE)]

            context = segments[idxs[0] - 1]["text"].strip() if idxs[0] > 0 else None
            retry = self._run(self.escalation_model_name, audio_slice, initial_prompt=context)
            retry_segments = offset_segments(
                [dict(s) for s in retry["segments"]],
                slice_start,
                self.escalation_model_name,
            )

            original = [segments[i] for i in idxs]
            original_score = candidate_score(original)
            retry_score = candidate_score(retry_segments)
            winner = "escalation" if retry_score > original_score else "base"
            escalation_log.append(
                {
                    "span": [round(start, 2), round(end, 2)],
                    "reasons": sorted({r for s in original for r in suspicion_reasons(s)}),
                    "base_text": " ".join(s["text"].strip() for s in original),
                    "escalated_text": " ".join(s["text"].strip() for s in retry_segments),
                    "base_score": round(original_score, 3),
                    "escalated_score": round(retry_score, 3),
                    "winner": winner,
                }
            )
            if winner == "escalation":
                segments[idxs[0]: idxs[-1] + 1] = retry_segments

        for i, seg in enumerate(segments):
            seg["id"] = i
        return segments, escalation_log


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def build_output(
    audio_path: Path,
    segments: list[dict],
    escalation_log: list[dict],
    reference_report: ReferenceReport | None,
    pipeline_info: dict,
) -> dict:
    out_segments = []
    for seg in segments:
        out_segments.append(
            {
                "id": seg.get("id", 0),
                "start": round(float(seg["start"]), 3),
                "end": round(float(seg["end"]), 3),
                "text": seg["text"],
                "confidence": round(segment_confidence(seg), 3),
                "model": seg.get("model"),
                "escalated": bool(seg.get("escalated")),
                "words": [
                    {
                        "word": w["word"],
                        "start": round(float(w["start"]), 3),
                        "end": round(float(w["end"]), 3),
                        "probability": round(float(w.get("probability", 0.0)), 3),
                        **({"corrected": True, "original": w["original"]}
                           if w.get("corrected") else {}),
                    }
                    for w in seg.get("words") or []
                ],
            }
        )

    doc = {
        "schema": "riffkit-transcript-v1",
        "audio": str(audio_path),
        "language": pipeline_info.get("language", "en"),
        "pipeline": pipeline_info,
        "text": "".join(s["text"] for s in segments).strip(),
        "segments": out_segments,
        "escalations": escalation_log,
    }
    if reference_report is not None:
        doc["reference"] = {
            "corrections": reference_report.corrections,
            "unmatched_reference_words": reference_report.unmatched_reference,
            "unmatched_transcript_words": reference_report.unmatched_transcript,
        }
    return doc


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Adaptive Whisper transcription for isolated vocal stems."
    )
    parser.add_argument("audio", help="Vocal stem audio file (mp3/wav/…)")
    parser.add_argument("--output", "-o", help="Output JSON path (default: alongside audio)")
    parser.add_argument("--base-model", default="small", help="Whisper model for the base pass")
    parser.add_argument(
        "--escalation-model",
        default="medium",
        help="Larger model for suspicious spans (downloads on first use)",
    )
    parser.add_argument(
        "--no-escalation",
        action="store_true",
        help="Single-pass only; skip per-segment escalation",
    )
    parser.add_argument("--lyrics", help="Reference lyric sheet (.txt) for disambiguation")
    parser.add_argument("--language", default="en")
    args = parser.parse_args()

    audio_path = Path(args.audio).expanduser()
    if not audio_path.exists():
        print(f"error: audio file not found: {audio_path}", file=sys.stderr)
        return 1

    reference_words = None
    if args.lyrics:
        lyrics_path = Path(args.lyrics).expanduser()
        if not lyrics_path.exists():
            print(f"error: lyric sheet not found: {lyrics_path}", file=sys.stderr)
            return 1
        reference_words = parse_reference_lyrics(lyrics_path.read_text(encoding="utf-8"))

    escalation_model = None if args.no_escalation else args.escalation_model
    transcriber = AdaptiveTranscriber(args.base_model, escalation_model, args.language)
    segments, escalation_log = transcriber.transcribe(audio_path)

    reference_report = None
    if reference_words:
        reference_report = apply_reference_lyrics(segments, reference_words)
        if reference_report.corrections:
            print(
                f"[transcribe] {len(reference_report.corrections)} word(s) corrected "
                "against the reference sheet",
                file=sys.stderr,
            )

    doc = build_output(
        audio_path,
        segments,
        escalation_log,
        reference_report,
        pipeline_info={
            "base_model": args.base_model,
            "escalation_model": escalation_model,
            "language": args.language,
            "reference_lyrics": args.lyrics or None,
        },
    )

    output_path = Path(args.output) if args.output else audio_path.with_suffix(".json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[transcribe] wrote {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
