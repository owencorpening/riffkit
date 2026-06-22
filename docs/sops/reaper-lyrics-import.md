# REAPER Lyrics Import SOP

Use this when you already have timestamped lyric JSON and want it on the `Lyrics` track in REAPER.

## Inputs

- A REAPER project with a track named exactly `Lyrics`
- Timestamped transcription JSON from OpenAI or legacy compatible JSON

## Procedure

1. Open the song project in REAPER.
2. Confirm a track named `Lyrics` exists.
3. In REAPER, open the Action List.
4. Load and run `lyrics-sync/InsertLyrics.lua`.
5. Pick the transcription JSON when the file dialog appears.

## Expected Result

- Timed items are created on the `Lyrics` track
- Each item note shows the current lyric and a preview of the next lyric

## Notes

- `InsertLyrics.lua` accepts OpenAI `segments` and `words` directly.
- Legacy `transcription` arrays are still accepted for compatibility.
- If nothing appears, check the REAPER console and verify the `Lyrics` track name exactly.

## Follow-up

- Use the lyric viewer or normal REAPER playback to check line timing against the vocal phrasing.
