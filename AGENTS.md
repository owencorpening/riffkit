# Instructions for AI coding agents

You are helping someone use riffkit: it turns a song file into a REAPER
practice project (stems, original mix and timed lyrics, one project per
song), and can first split a concert recording into song files. Read
README.md for what it does. This file says how to run it for the user
safely.

## Before anything

- **Ask for the audio.** Get the path to the user's song or concert file.
  riffkit is only for audio the user has the right to use; never download
  music for them from streaming sites unless they say they own the rights.
- **Check the tools:** `python3 --version` (3.10 or newer), `ffmpeg -version`,
  `ffprobe -version`. If ffmpeg is missing, tell the user how to install it
  for their system and stop; don't install system packages without asking.
- **Check memory:** stem separation and transcription need several GB free.
  On Linux run `free -h`; if less than 4 GB is available, tell the user and
  suggest closing a browser before going on.
- **REAPER** must be installed to open the result. You don't need it to run
  riffkit.

## Install (once)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

This downloads PyTorch and model files: several GB, and it can take a while.
Tell the user before you start.

## Run

**One song** (the usual case):

```bash
.venv/bin/python riffkit.py "<song file>" --output "<output folder>"
```

Prints the path of the `.RPP` to open in REAPER. Expect several minutes per
song on a CPU. Run one song first and let the user check the result in
REAPER before running a batch.

**A concert, split by pauses**, then each song as above:

```bash
.venv/bin/python riffkit.py "<concert file>" --split-concert --output "<songs folder>"
```

**A concert, split by setlist:** needs a setlist file (format in README.md)
and a transcript of the concert:

```bash
.venv/bin/python scripts/transcribe_concert.py "<concert file>" "<concert>.json"
.venv/bin/python riffkit.py "<concert file>" --split-concert --setlist-mode \
    --song-list "<setlist.txt>" --transcript "<concert>.json" --output "<songs folder>"
```

Transcribing takes roughly half the length of the concert. Show the user the
printed boundaries list, and point out every row marked `CHECK`: those are
the songs whose start or end they should listen to. If they correct times in
the written `boundaries.txt`, re-cut with `--boundaries <file>` instead of
`--setlist-mode`.

## Rules

- Never commit audio, stems, transcripts of recordings or REAPER projects
  to this repository, and never upload them anywhere.
- Don't change riffkit's code to get a run working. If something fails,
  show the user the error and what you think it means.
- Report what you actually ran, where the output is, and how long it took.
- Poor stems usually mean a poor recording (an audience tape, a
  low-bitrate copy). Say so plainly instead of trying model after model.
