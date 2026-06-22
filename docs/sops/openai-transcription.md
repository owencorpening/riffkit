# OpenAI Transcription SOP

Use this when you have a vocals stem and want timestamped lyric data for `InsertLyrics.lua`.

## Inputs

- `vocals.mp3` from the stem folder
- An `OPENAI_API_KEY`

## Command

From the repo root or any shell session with the key exported:

```bash
export OPENAI_API_KEY="your_api_key_here"

curl https://api.openai.com/v1/audio/transcriptions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: multipart/form-data" \
  -F file="@/home/owen/Music/riffkit-runs/song-name/htdemucs/song-title/vocals.mp3" \
  -F model="whisper-1" \
  -F response_format="verbose_json" \
  -F "timestamp_granularities[]=word" \
  -o "/home/owen/Music/riffkit-runs/song-name/song-title.transcription.json"
```

## Expected Output

- One JSON file saved in your song work area or any nearby location you want to browse from REAPER
- The JSON should contain OpenAI-style `segments` or `words` data

## Notes

- This pass uses `whisper-1`.
- Keep the JSON in your homedir workflow area so you can pick it up in REAPER later.
- If you only need coarse lyric blocks, `segments` is enough; if you want word-level timing, request word timestamps.

## Follow-up

- Open REAPER.
- Run `InsertLyrics.lua`.
- Select the saved JSON file.
