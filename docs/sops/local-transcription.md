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
- If you want a different balance of speed and accuracy, change `--model` to `base`, `small`, `medium`, or another installed Whisper model.
- Keep the JSON in your homedir workflow area so you can pick it up in REAPER later.

## Follow-up

- Open REAPER.
- Run `InsertLyrics.lua`.
- Select the saved JSON file.
