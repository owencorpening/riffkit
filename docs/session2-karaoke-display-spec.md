# riffkit Session 2: Karaoke Playback Display — Fable 5 Eval (or fallback model)

## Purpose of this session

Session 2 of 2. Builds on the timestamped lyric output from Session 1
(adaptive transcription + disambiguation). This piece is lower-risk and
lower-difficulty than Session 1 — if the Fable 5 eval window runs out
before this session happens, this is fine to finish on a standard model.

## Scope

Drive karaoke-style playback in sync with REAPER transport position:

- Current line displayed prominently
- Next line visible/queued (standard karaoke convention — performers need
  to see what's coming, not just what's playing)
- Synced to REAPER playback position in real time

## Input

Timestamped lyric data produced by Session 1. Format TBD by whatever
Session 1 actually produced — consume it as-is rather than forcing it
into a predetermined shape.

## No constraints on implementation

Any language, any library. Prior art below is reference only.

## Prior art (context, not constraints)

- `Reaper_InsertLyrics` prototype used empty MIDI items on a "Lyrics"
  track (words in item notes) plus the x-raym script to render karaoke
  display in a browser. This worked but was first-draft quality with no
  "next line" logic — it only ever showed the current line.
- Church-band use case is the anchor scenario: lyrics displayed on a large
  TV/monitor for rehearsal and live service playback. Design for that
  context — readable at a distance, clean transitions between lines, no
  clutter.

## Requirements

- Real-time sync accuracy: line changes should track actual playback
  position, not drift or lag noticeably.
- "Next line" should be visually distinct from "current line" (e.g. dimmed,
  smaller, or otherwise clearly secondary) so performers aren't confused
  about which line is live.
- Should degrade gracefully if playback jumps (seek/scrub) — display
  should catch up to the new position, not get stuck on the old line.

## Deliverable for this session

- Working karaoke display driven off REAPER transport + Session 1's
  timestamped lyric data.
- Notes on what browser/display approach was used and why, so it's
  reusable across songs without per-song reconfiguration.
