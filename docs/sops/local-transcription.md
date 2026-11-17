# Local Whisper Transcription SOP

Use this when you have a vocals stem and want timestamped lyric data for `InsertLyrics.lua` without relying on a paid API.

## Inputs

- `vocals.mp3` from the stem folder
- The repo virtualenv with `openai-whisper` installed
- `ffmpeg` on your PATH

## Setup

Install the project dependencies if Whisper is not available yet:

```bash
.venv/bin/pip install -r requirements.txt
```

## Command

From the repo root:

```bash
.venv/bin/whisper "/home/owen/Music/riffkit-runs/song-name/htdemucs/song-title/vocals.mp3" \
  --model small \
  --output_format json \
  --word_timestamps True \
  --output_dir "/home/owen/Music/riffkit-runs/song-name"
```

## Expected Output

- A JSON file written into the chosen output directory
- The JSON should contain timestamped transcription data that `InsertLyrics.lua` can read

## Notes

- This is the default path for the repo now.
- Hosted OpenAI transcription was tried for `08 - Foxy Lady` on `2026-06-22` and failed with `insufficient_quota`, so this local path is the working default.
- If you want a different balance of speed and accuracy, change `--model` to `base`, `small`, `medium`, or another installed Whisper model.
- Keep the JSON in your homedir workflow area so you can pick it up in REAPER later.

## Whole-concert transcription (chunked)

For a full concert recording, use the chunked faster-whisper script instead of the `whisper` command above:

```bash
.venv/bin/python scripts/transcribe_concert.py \
  data/gothenburg-1970-09-01.mp3 \
  /home/owen/whisper_runs/gothenburg.json \
  --model small --chunk-minutes 10
```

- The audio must be chunked. Transcribing a whole concert in one pass runs this machine out of memory; the script decodes with `ffmpeg` and feeds the model 10-minute chunks, with timestamps offset back to absolute concert time.
- It took 51 minutes for a 90-minute concert on this machine (`small` model, CPU).
- Keep `--chunk-minutes` at 10; that is the tested setting. Word timestamps crashed faster-whisper on very short chunks (1 minute).
- Transcripts of copyrighted recordings live in `data/` (for test fixtures, `data/fixtures/`) and are never committed.
- The JSON is rewritten after every chunk, so an interrupted run keeps everything up to the last finished chunk.
- Progress lines are printed as segments arrive; the run ends with `=== finished in N seconds ===`.
- Needs `faster-whisper` (in `requirements.txt`, only used for transcription).

## Follow-up

- Open REAPER.
- Run `InsertLyrics.lua`.
- Select the saved JSON file.
