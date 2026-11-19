# Get a Song File SOP

Use this when you want a song's audio as a file riffkit can process.

riffkit is for music you have the right to use. Nothing made from other
people's music is published.

## Inputs

- A YouTube URL for the song
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [ffmpeg](https://ffmpeg.org/) installed

## Command

```bash
yt-dlp -f bestaudio -x --no-playlist \
  -o "~/Music/riffkit-sources/%(title)s.%(ext)s" "YOUTUBE-URL"
```

- `-f bestaudio` picks the best audio-only stream.
- `-x` keeps only the audio, without re-encoding it. From YouTube that is
  usually an `.opus` file (sometimes `.m4a`); riffkit accepts both.
- `--no-playlist` matters when the URL contains `&list=`: without it,
  yt-dlp downloads the whole playlist instead of the one song.
- Put the URL in quotes, because `&` means something to the shell.
- Change the `-o` folder to wherever you keep your source songs.

## If You Already Have a .webm

A `.webm` downloaded earlier usually holds Opus audio. Repackage it as
`.opus` without re-encoding:

```bash
ffmpeg -i "in.webm" -vn -c:a copy "out.opus"
```

`-vn` drops any video; `-c:a copy` copies the audio as it is, so there is
no quality loss.

## Formats riffkit Accepts

WAV, MP3, FLAC, M4A and Opus.

## Follow-up

Turn the song into a REAPER project:

```bash
.venv/bin/python riftkit.py "<song file>" --output <dir>
```

See [Stem Separation](stem-separation.md) for the details.
