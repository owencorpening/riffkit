# riffkit Session 1: Adaptive Vocal Transcription + Lyric Disambiguation — Fable 5 Eval

## Purpose of this session

Bounded eval of Claude Fable 5, session 1 of 2, during the free-access
window (through July 19, 2026, 50% weekly quota cap). This session is
scoped to the hardest, highest-value piece of the lyric-sync pipeline:
maximally accurate, disambiguated transcription against an isolated vocal
stem. Session 2 (separate spec) covers karaoke playback display, built on
whatever this session produces.

Front-loading this piece deliberately: if the eval window runs out before
session 2 happens, the harder problem is the one that got solved.

## Scope

Take an isolated vocal stem (output of riffkit's stem-separation step) and
produce the most accurate possible timestamped lyric transcription,
including resolving acoustically-ambiguous or slurred lines correctly.

Output format: whatever is cleanest to consume downstream (JSON with
word/segment-level timestamps is the likely default, matching the prior
Whisper-JSON convention below) — not fixed, open to a better structure if
one emerges.

## No constraints on implementation

Any language, any library, any architecture. Full rewrite of prior art is
fine and likely preferable. Nothing here is scaffolding to preserve for
its own sake.

## Prior art (context, not constraints)

- `owencorpening/Reaper_InsertLyrics` (archived prototype): ffmpeg → 16kHz
  mono WAV → whisper.cpp (ggml-small.en model, single pass, single config)
  → JSON. Known to be first-draft quality, no disambiguation logic.
- `owencorpening/riffkit`, `lyrics-sync/` folder: live home for this work.

## Priority requirement: maximize accuracy, not speed

This is the entire point of the session.

- **Adaptive model/config selection per segment.** Not every vocal passage
  needs the same Whisper model or settings. Clear, sustained,
  well-enunciated segments may transcribe fine on a smaller/faster model.
  Fast phrasing, melisma, quiet/breathy delivery, harmonies, and ad-libs
  may need a larger model (e.g. whisper large-v3 or equivalent), different
  decoding parameters (beam size, temperature, language hints), or
  multiple passes reconciled against each other. Design for per-segment
  escalation, not one global setting for the whole track.
- **Resolving slurred/ambiguous lyrics is the single biggest value-add.**
  Target case: a line that could transcribe as "Hello Boston" when the
  actual lyric is "Hello Austin" — acoustically close, semantically
  different, and a naive single-pass run is prone to exactly this kind of
  confident-but-wrong output. Worth real engineering effort: consider
  cross-checking ambiguous segments against multiple model runs,
  confidence scores, phonetic similarity, or (if available) a reference
  lyric sheet for the song to disambiguate against known-correct lyrics
  rather than guessing from audio alone.
- Coverage over speed is the right tradeoff — this is a batch/prep-time
  tool (songs prepped days before a service), not real-time. Slower and
  more accurate beats fast and wrong.

## Deliverable for this session

- Working (or clearly scoped, if it can't fully finish) implementation of
  the adaptive-model transcription + disambiguation pipeline.
- Honest assessment of what's still unsolved for the "Hello Austin, not
  Boston" class of problem if not fully solved live (e.g. "needs a
  reference lyric sheet," "needs a larger local model than what's
  available," etc.)
- Clean, documented output format handed off, so session 2 can consume it
  without re-deriving context.
- Notes on what was built vs. stubbed, so this can resume cleanly on a
  different model later if needed.
