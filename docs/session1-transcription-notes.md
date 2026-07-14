# Session 1 Handoff: Adaptive Transcription Pipeline

Implements [session1-transcription-spec.md](session1-transcription-spec.md).
This doc is the handoff for session 2 (karaoke display): what was built, the
output format to consume, and what remains open.

## What was built

`lyrics-sync/transcribe_adaptive.py` — a single-file pipeline, stdlib +
`openai-whisper` only (no new dependencies):

1. **Base pass** — whole vocal stem through a fast Whisper model
   (default `small`), word timestamps on, beam search (`beam_size=5`).
2. **Per-segment suspicion scoring** — a segment is flagged when any of:
   `avg_logprob < -0.8`, any word probability `< 0.4`, mean word
   probability `< 0.6`, `compression_ratio > 2.4` (repetition /
   hallucination), `no_speech_prob > 0.6`, or Whisper fell back to
   `temperature > 0.2`.
3. **Escalation** — adjacent suspicious segments are merged into spans
   (padded ±0.35 s), the audio slice is re-run through a larger model
   (default `medium`) with the preceding accepted lyric as
   `initial_prompt` context. The base and escalated candidates are scored
   (mean word probability, halved on repetition) and the winner keeps the
   span; escalated timestamps are shifted back into track time.
4. **Reference-sheet disambiguation** — with `--lyrics sheet.txt`, the
   transcript is word-aligned to the sheet (`difflib` opcodes over
   normalized words). Mismatched pairs are compared with a blended
   spelling + phonetic-key similarity (compact metaphone-style:
   `Boston → PSTN`, `Austin → ASTN`); pairs scoring ≥ 0.55 are treated as
   mishearings and replaced with the sheet's word **keeping the
   audio-derived timestamps**. A spelling-similarity floor (0.4) guards
   against the lossy phonetic keys on short words ("that"/"to" both key
   to `T` — caught in real-file smoke testing). Genuine mismatches
   (ad-libs, skipped verses) are left alone and reported, never
   force-fitted.

### Usage

```bash
.venv/bin/python lyrics-sync/transcribe_adaptive.py vocals.mp3 \
  --output vocals.json \
  --base-model small --escalation-model medium \
  --lyrics reference_lyrics.txt        # optional but recommended
```

`--no-escalation` gives a single-pass run. `medium` (~1.5 GB) downloads on
first use; on a CPU-only box expect escalation to be slow — that is the
spec'd tradeoff (batch/prep-time tool, accuracy over speed).

Tests: `pytest tests/test_transcribe_adaptive.py` (pure functions, no
model downloads).

## Output format (consume this in session 2)

`riffkit-transcript-v1` JSON. The `segments` array is Whisper-shaped, so
`InsertLyrics.lua` reads it unchanged; everything else is additive.

```jsonc
{
  "schema": "riffkit-transcript-v1",
  "audio": "/path/to/vocals.mp3",
  "language": "en",
  "pipeline": { "base_model": "small", "escalation_model": "medium",
                "language": "en", "reference_lyrics": "sheet.txt" },
  "text": "Hello Austin ...",              // full transcript, one string
  "segments": [
    {
      "id": 0,
      "start": 1.0, "end": 2.0,            // seconds
      "text": " Hello Austin",
      "confidence": 0.93,                  // mean word probability, 0–1
      "model": "small",                    // which model produced this segment
      "escalated": false,
      "words": [
        { "word": " Hello", "start": 1.0, "end": 1.4, "probability": 0.98 },
        { "word": " Austin", "start": 1.5, "end": 2.0, "probability": 0.41,
          "corrected": true, "original": "Boston" }   // only present when corrected
      ]
    }
  ],
  "escalations": [                          // audit log, one per escalated span
    { "span": [12.3, 15.1], "reasons": ["low_avg_logprob", "weak_word"],
      "base_text": "...", "escalated_text": "...",
      "base_score": 0.42, "escalated_score": 0.71, "winner": "escalation" }
  ],
  "reference": {                            // only when --lyrics was given
    "corrections": [ { "heard": "Boston", "corrected_to": "Austin",
                       "similarity": 0.71, "start": 1.5 } ],
    "unmatched_reference_words": ["beautiful"],   // in sheet, never heard
    "unmatched_transcript_words": ["yeah"]        // heard, not in sheet
  }
}
```

Session-2 guidance: render `segments[].words[]` for word-level karaoke
highlighting; `confidence` and `corrected` are available if you want to
style uncertain or sheet-corrected words differently.

## Honest assessment: the "Hello Austin, not Boston" problem

- **Solved when a reference lyric sheet is available.** The
  phonetic-alignment path substitutes acoustically-close mishearings
  reliably (unit-tested on the exact Boston/Austin case) and keeps
  timestamps. This is the recommended workflow: lyric sheets are easy to
  obtain for worship/cover material.
- **Partially mitigated without a sheet.** Escalation catches
  low-confidence mishearings, but a *confidently* wrong word ("Boston" at
  p=0.9) is flagged by nothing — no audio-only heuristic in this pipeline
  will catch it. That class of error genuinely needs external knowledge
  (a sheet, or an LLM pass with song context).
- The phonetic key is a compact metaphone approximation, English-biased.
  Good enough for the target material; a real G2P model would be better
  but adds heavy deps.
- **Smoke test** (75 s slice of the Stockholm-1970 `08 - Foxy Lady`
  vocals stem, `tiny.en → small` ladder to stay on cached models): all
  mechanics worked — 5 spans escalated, winner selection behaved sensibly
  (kept base when the retry was empty or worse, took the escalation when
  clearly better), sheet corrections applied, valid JSON emitted. Content
  quality on that slice was poor, as expected: it is mostly ad-libs and
  stage banter on a live recording, run through the smallest model. The
  real accuracy run is the full song on `small → medium` with a proper
  lyric sheet (tracked in NEXT.md).

## Built vs. stubbed

| Piece | Status |
| --- | --- |
| Base pass, word timestamps, beam search | Built, smoke-tested on real stem |
| Suspicion scoring + span merging | Built, unit-tested |
| Per-span escalation with context prompt | Built, smoke-tested (tiny.en→small ladder) |
| Reference-sheet phonetic disambiguation | Built, unit-tested |
| Output schema + InsertLyrics.lua compatibility | Built, unit-tested |
| Timestamps for sheet words never transcribed (interpolation) | **Stubbed** — reported in `unmatched_reference_words`, no timing |
| Audio-only disambiguation of confident mishearings | **Unsolved** — needs a sheet or an LLM rescoring pass (see above) |
| riftkit.py integration (auto-run after stem split) | **Stubbed** — riftkit.py prints the command to run manually |
| Multi-candidate ensembling (>2 models / temperature sweep) | Not built — escalation is a 2-candidate compare; the plumbing (candidate_score) generalizes if wanted |

The old `lyrics-sync/transcribe.py` (paid-API placeholder) was removed;
this pipeline replaces it.
