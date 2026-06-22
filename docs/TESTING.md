# riffkit Testing Plan

## Goal

`riffkit` should be tested as a music workflow, not just as a set of files.

That means the test suite should cover:

* Python CLI behavior
* REAPER Lua script invariants
* sample input data
* expected lyric or item-note output
* end-to-end workflow smoke tests where possible

## Fixture Philosophy

Use small, owned, or generated assets whenever possible.

Prefer:

* short MP3 or WAV clips
* short lyric samples
* small JSON transcription fixtures
* tiny REAPER template files

Avoid:

* long copyrighted songs
* large binary fixtures that make the repo heavy
* tests that depend on REAPER being installed in CI unless they are explicitly marked as manual

## Suggested Layout

```text
tests/
  fixtures/
  audio/
    church-band-short.mp3
    practice-drums-short.wav
    stockholm_excerpt.mp3
  lyrics/
    church-band-lyrics.txt
    church-band-whisper.json
    stockholm_excerpt.txt
  stockholm_split/
    segments.json
    01 - Introduction.mp3
    02 - Fire Part 1.mp3
    03 - Drum Solo.mp3
  reaper/
    stem_template.RPP
    lyrics_template_note.txt
```

## Test Layers

### 1. Unit Tests

These should stay fast and deterministic.

Examples:

* `separate_stems()` passes the right arguments to Demucs
* `copy_template()` copies the template to the expected location
* helper functions for lyric parsing and marker parsing return the expected values

### 2. Fixture Tests

These use small real files from `tests/fixtures/`.

Examples:

* a sample MP3 produces the expected output path layout
* a sample lyric file produces the expected item-note formatting
* a sample timestamped transcription JSON file matches the expected lyric import structure

### 3. Golden-Output Tests

These compare actual output to expected output.

Examples:

* generated lyric notes match a known HTML format
* imported stems land on the expected REAPER track names
* one song produces one project folder / one REAPER project

### 4. Smoke Tests

These are small end-to-end checks.

Examples:

* one sample audio file goes through the Python CLI and produces the expected folder structure
* one sample transcription JSON can be fed through the lyric import path

## First Targets

The first useful test fixtures should probably be:

1. One short MP3 or WAV clip for stem-separation tests
2. One matching lyrics text file
3. One Whisper-style JSON transcription sample
4. One REAPER template file stub for copy/placement tests
5. One concert-style clip with a silence gap for split testing

## Notes on REAPER

REAPER-specific runtime tests will probably remain partly indirect in CI.

That is fine. The current approach is:

* verify Lua scripts exist
* verify critical strings and conventions are present
* test pure helper logic in Python
* reserve full REAPER execution for manual or local smoke testing

## Practical Rule

If a test fixture would be painful to explain to a collaborator, it is probably too big.
