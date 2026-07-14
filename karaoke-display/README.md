# karaoke-display: REAPER-synced lyric display

Session 2 of the lyric-sync pipeline (see
[docs/session2-karaoke-display-spec.md](../docs/session2-karaoke-display-spec.md)).
Shows the **current line** large with word-level highlighting and the
**next line** dimmed below it, synced to REAPER's playback position —
designed to be readable on a TV across a rehearsal room.

## How it works (and why this approach)

`karaoke.html` is a single self-contained page with no dependencies and
no server of its own. It uses **REAPER's built-in web browser
interface**: REAPER serves the page and exposes transport state at
`/_/TRANSPORT`, which the page polls 10×/second and extrapolates with
the wall clock between polls, so word highlighting is smooth. Every
frame maps position → line from scratch (binary search), so
seeking/scrubbing anywhere in the song snaps the display to the right
line on the next frame — it cannot get stuck.

This was chosen over an OSC bridge or a Node/websocket server because
it needs zero extra infrastructure: REAPER *is* the web server. The
prior-art x-raym karaoke script used the same interface, but only
showed the current line; this adds next-line queueing, word
highlighting, seek recovery, and gap handling.

Input is the `riffkit-transcript-v1` JSON from
[lyrics-sync/transcribe_adaptive.py](../lyrics-sync/transcribe_adaptive.py)
(format documented in
[docs/session1-transcription-notes.md](../docs/session1-transcription-notes.md)).
Plain Whisper JSON with `segments` also works — only `segments[].start/end/text`
and optionally `words[]` are read.

## One-time REAPER setup

1. REAPER → **Options → Preferences → Control/OSC/web → Add** →
   **Web browser interface**. Keep the default port (8080).
2. Note the *Web root* folder it shows (usually
   `~/.config/REAPER/reaper_www_root/`). Create it if needed.
3. Link this page into it (symlink keeps it updated with the repo):

   ```bash
   mkdir -p ~/.config/REAPER/reaper_www_root/songs
   ln -s ~/dev/riffkit/karaoke-display/karaoke.html ~/.config/REAPER/reaper_www_root/
   ```

## Per-song use

1. Drop the song's transcript JSON into
   `~/.config/REAPER/reaper_www_root/songs/`.
2. Open `http://localhost:8080/karaoke.html?src=songs/my-song.json` on
   the display machine (any device on the LAN works —
   `http://<reaper-box>:8080/…`).
3. Press play in REAPER. Fullscreen the browser (F11) on the TV.

No `?src=` param → the page offers a file picker / drag-and-drop
instead, so ad-hoc use needs no file copying at all.

## Display behavior

- **Current line**: large, bold; words turn amber as they are sung
  (word timestamps from the transcript).
- **Next line**: dimmed and smaller below — clearly secondary.
- **Instrumental gaps**: after a line has been finished for 1.5 s with
  nothing imminent, the current slot shows `♪ ♪ ♪` and the upcoming
  line stays queued. Short inter-line gaps do not flicker.
- **Seek/scrub/loop**: display re-resolves from transport position every
  frame; jumps recover immediately.
- **Status chip** (bottom-left): green dot = connected to REAPER,
  red = transport unreachable (display freezes rather than drifting),
  blue = demo mode; plus song name and position.

## Testing without REAPER

Open the page with `?demo=1` (any static server, e.g.
`python3 -m http.server` in this folder): an internal clock plays the
song — **space** pauses, **←/→** seek ±5 s. Useful for checking a
transcript's line breaks before rehearsal.
