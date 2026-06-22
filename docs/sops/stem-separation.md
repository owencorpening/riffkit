# Stem Separation SOP

Use this when you have a single song file and want a Demucs stem folder plus the REAPER template beside it.

## Inputs

- One song file, usually MP3 or WAV
- The repo virtualenv at `.venv/`

## Command

From the repo root:

```bash
.venv/bin/python riftkit.py "/path/to/song.mp3" --output "/home/owen/Music/riffkit-runs/song-name" --no-lyrics
```

## Expected Output

- A folder like `/home/owen/Music/riffkit-runs/song-name/htdemucs/<song title>/`
- Stem files such as `bass.mp3`, `drums.mp3`, `other.mp3`, and `vocals.mp3`
- A REAPER template at `/home/owen/Music/riffkit-runs/song-name/htdemucs/stem_template.RPP`

## Notes

- This step is outside REAPER.
- If the output folder already exists, review it before re-running so you do not confuse old and new results.
- The script uses Demucs through the repo virtualenv.

## Follow-up

- Open `stem_template.RPP` in REAPER.
- Load `import_stems.lua`.
- Select any file in the stem folder when prompted.
