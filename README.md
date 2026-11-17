# riffkit

Turn a song into a REAPER practice project: the song separated into
stems, with the lyrics already timed to the music. One project per song.
Have a whole concert instead? riffkit can split it into songs first.

riffkit is a tool for guitarists (and anyone else) who learn songs by
playing along: mute your own part, slow the song down without changing
its pitch, loop the hard bit, and read the words as they are sung.

> **Use it only on audio you have the right to use.** riffkit works on
> your own files. This repository contains code only: no recordings,
> stems, transcripts or projects made from anyone else's music.

***

### What it does

There are two ways in. Most of the time you start with a song file. If
you have a whole concert recording, riffkit splits it into song files
first, and each song then goes through the same steps.

```
song file ──────────────────────────┐
                                    ▼
concert ──► split into songs ──► each song ──► stems ──► REAPER project
            (optional)                        (vocals,   (one per song:
                                               drums,     stems + original
                                               bass,      mix + Lyrics)
                                               other)
```

**Starting from a song:**

1. **Stem separation:** Demucs (`htdemucs_ft` by default) splits the song
   into four stems, as WAV files: vocals, drums, bass, and **other**.
   *Other* is everything that isn't vocals, drums or bass: in most rock
   songs that means the guitar, plus any keyboards, horn or string
   sections, and other instruments. For a separate
   guitar stem, use `--stem-model htdemucs_6s`, which also splits out
   guitar and piano, at some cost in quality.
2. **Lyrics:** Whisper transcribes the vocals stem; the transcript is
   cleaned up (long lines split, invented text over silent stretches
   dropped, each line moved to where the voice comes in).
3. **REAPER project:** one `.RPP` **for each song**, with Vocals, Drums,
   Bass and Other on their own tracks, the original mix on a muted track,
   and the lyrics on a Lyrics track. Open it and play.

**Starting from a concert** (only if you don't already have song files):
riffkit cuts the recording into one file per song, then each song goes
through steps 1 to 3 and gets its own project. Three ways to find where
songs start and end:

* **Pause detection:** songs separated by silence.
* **Setlist mode:** give it the setlist and it finds one boundary per
  song, even where the band barely pauses. Uses a Whisper transcript of
  the concert to keep each title on the right song.
* **Your own marks:** a boundaries file with a start and end per song,
  for example from markers you placed in REAPER. No detection at all.

### Quick start

You need Python 3, `ffmpeg` and `ffprobe` on your PATH, and
[REAPER](https://www.reaper.fm/).

```bash
git clone https://github.com/owencorpening/riffkit
cd riffkit
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**A song to a REAPER project** (the usual case; no concert needed):

```bash
.venv/bin/python riftkit.py "My Song.wav" --output ~/riffkit-projects
```

Then open `~/riffkit-projects/htdemucs_ft/My Song/My Song.RPP` in REAPER.
Input can be WAV, MP3, FLAC, M4A or Opus. Run it once per song; each song
gets its own folder and its own project.

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

Then run each song file through the song command above to get one
REAPER project per song.

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
| **Learning** | Learn one part by isolating drums, guitar (the Other stem), bass or vocals. | Stems you can mute or turn down, played in REAPER, which can slow down without changing pitch and loop a section. |
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
