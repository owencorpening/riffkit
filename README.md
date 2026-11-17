# riffkit

Split live concerts into songs, separate each song into stems, and build
a REAPER practice project with the lyrics already timed to the music.

riffkit is a tool for guitarists (and anyone else) who learn songs by
playing along: mute your own part, slow the song down without changing
its pitch, loop the hard bit, and read the words as they are sung.

> **Use it only on audio you have the right to use.** riffkit works on
> your own files. This repository contains code only: no recordings,
> stems, transcripts or projects made from anyone else's music.

***

### What it does

```
concert recording ──► song files ──► stems ──► REAPER project
   (optional)          (one per        (vocals,    (stems + original
                        song)           drums,      mix + Lyrics track)
                                        bass,
                                        other)
```

1. **Song splitting** (optional): cut a long concert recording into one
   file per song. Three ways to find where songs start and end:
   * **Pause detection:** songs separated by silence.
   * **Setlist mode:** give it the setlist and it finds one boundary per
     song, even where the band barely pauses. Uses a Whisper transcript of
     the concert to keep each title on the right song.
   * **Your own marks:** a boundaries file with a start and end per song,
     for example from markers you placed in REAPER. No detection at all.
2. **Stem separation:** Demucs (`htdemucs_ft` by default) splits each song
   into vocals, drums, bass and other, as WAV files.
3. **Lyrics:** Whisper transcribes the vocals stem; the transcript is
   cleaned up (long lines split, invented text over silent stretches
   dropped, each line moved to where the voice comes in).
4. **REAPER project:** one `.RPP` per song with Vocals, Drums, Bass and
   Other on their own tracks, the original mix on a muted track, and the
   lyrics on a Lyrics track. Open it and play.

### Quick start

You need Python 3, `ffmpeg` and `ffprobe` on your PATH, and
[REAPER](https://www.reaper.fm/).

```bash
git clone https://github.com/owencorpening/riffkit
cd riffkit
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**One song to a REAPER project:**

```bash
.venv/bin/python riftkit.py "My Song.wav" --output ~/riffkit-projects
```

Then open `~/riffkit-projects/htdemucs_ft/My Song/My Song.RPP` in REAPER.
Input can be WAV, MP3, FLAC, M4A or Opus.

**A concert, split by pauses:**

```bash
.venv/bin/python riftkit.py concert.mp3 --split-concert --output ~/riffkit-songs
```

**A concert, split by its setlist:**

```bash
.venv/bin/python scripts/transcribe_concert.py concert.mp3 concert.json
.venv/bin/python riftkit.py concert.mp3 --split-concert --setlist-mode \
    --song-list setlist.txt --transcript concert.json --output ~/riffkit-songs
```

The printed boundaries list marks each song `ok` or `CHECK`. Listen to
the `CHECK` ones, correct any time in the written `boundaries.txt`, and
re-cut without detection:

```bash
.venv/bin/python riftkit.py concert.mp3 --split-concert \
    --boundaries ~/riffkit-songs/concert_songs/boundaries.txt --output ~/riffkit-songs
```

Then run each song file through the one-song command above.

### Setlist files

One song per line, in the order played. A line in parentheses is music
that isn't a song (a solo or a jam): riffkit finds it but writes no file.
Words after a `|` are hints: words you know are sung in that song, which
help riffkit recognise it in the transcript.

```
Setlist, in order:
(solo)
1. Spanish Castle Magic | waste your time
2. Killing Floor
3. Hear My Train A-Comin' | train
```

### What to expect

* **Recording quality decides stem quality.** Clean recordings (studio
  albums, official live releases) separate well. Audience tapes and
  low-bitrate copies do not, and no model fixes that. For those, the
  original mix with timed lyrics is still a useful practice project.
* **It is slow on a CPU.** Expect several minutes per song for stems and
  lyrics, and about 50 minutes to transcribe a 90-minute concert for
  setlist mode. It needs several GB of free memory.
* **Setlist mode is close, not perfect.** On the test concert it placed
  12 of 13 song starts and 12 of 13 song ends within a few seconds, and
  flagged the misses. Your own marks always override it.
* **Tested on Linux only.**

### Modes it is built for

| Mode | Goal | riffkit's role |
| :--- | :--- | :--- |
| **Learning** | Learn one part by isolating drums, guitar, bass or vocals. | Stems you can mute or turn down, played in REAPER, which can slow down without changing pitch and loop a section. |
| **Rehearsal** | Practice as a band. | One project per song, so each player can mute their own part. |
| **Performance** | Lyrics on a big screen. | A Lyrics track timed to the song; a karaoke display in `karaoke-display/`. |

### Example: church band

A band receives four songs a few days before a service. Each song becomes
its own REAPER project with stems and lyrics, so each player can mute
their own part and learn it against the rest, and the words can go on a
TV for rehearsal.

### Repository layout

| Path | What it is |
| :--- | :--- |
| `riftkit.py` | The main command. |
| `setlist_split.py` | Setlist-mode song splitting. |
| `reaper_project.py` | Writes the REAPER project. |
| `scripts/transcribe_concert.py` | Whisper transcript of a whole concert, in 10-minute pieces. |
| `lyrics-sync/` | Vocal transcription, transcript cleanup, REAPER lyrics scripts. |
| `stem-separation/` | Stem separation notes and the manual `import_stems.lua`. |
| `karaoke-display/` | A browser lyrics display synced to REAPER. |
| `docs/` | Use cases, roadmap, testing notes and step-by-step SOPs. |

### Philosophy

* **Built for me first.** Features arrive when I need them.
* **Shared without obligation.** Open source under the MIT license, with
  no support promises.
* **Modular.** Take the pieces you need.

*Historical note: this project was originally called Songster.*
