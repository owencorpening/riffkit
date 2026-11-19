# riffkit

[![tests](https://github.com/owencorpening/riffkit/actions/workflows/tests.yml/badge.svg)](https://github.com/owencorpening/riffkit/actions/workflows/tests.yml)

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
2. **Lyrics:** looked up when possible, heard otherwise (see
   [Where lyrics come from](#where-lyrics-come-from)). Heard lyrics come
   from Whisper transcribing the vocals stem; the transcript is cleaned
   up (long lines split, invented text over silent stretches dropped,
   each line moved to where the voice comes in).
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

You need Python 3, `ffmpeg` and `ffprobe` on your PATH, and REAPER.

**Install REAPER** from [reaper.fm/download.php](https://www.reaper.fm/download.php)
(Windows, macOS or Linux). The full program is free to evaluate for 60
days; see the REAPER site for licensing after that. riffkit itself
doesn't need REAPER to run. You need it to open the projects riffkit
makes.

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

### Where lyrics come from

riffkit takes the first of these that works:

1. **A `.lrc` file next to the song** with the same name, such as
   `My Song.lrc` beside `My Song.opus`. Use this for your own timed lyrics.
2. **[LRCLIB](https://lrclib.net)**, a free, community-built library of
   timed lyrics. riffkit makes one lookup by artist, title and the song's
   length, and uses the result only if it has timed lyrics and its length
   is within 2 seconds of your file's. The result is saved as a `.lrc`
   next to the song, so it is never looked up twice.
3. **Hearing them:** Whisper transcribes the vocals stem. This works with
   any song but gets many words wrong, especially on live recordings.

Artist and title come from the file's tags, or give them yourself:

```bash
.venv/bin/python riftkit.py "Song.opus" --artist "Some Band" --title "Some Song"
```

Timed lyrics are made for one copy of a recording, and another upload of
the same song can start a little earlier or later. So for lyrics from a
`.lrc` file or LRCLIB, riffkit measures where the voice comes in on the
vocals stem and shifts every line to match (it prints the amount, and
leaves the lyrics alone when they already line up or the lines disagree).

Those lyrics have a time for each line only, so riffkit also hears the
vocals stem and gives each word the time it was heard. Words Whisper
missed are spaced out between the ones it caught. This lets the karaoke
display light up the words one by one, and takes about as long as hearing
the lyrics would. riffkit prints how many words got a heard time.

Other options: `--lyrics-from auto|lrc|lrclib|hear` picks one source
(default `auto`, the order above), `--lyrics-offset 0.3` sets the shift
yourself instead (later by 0.3 seconds; negative is earlier; `0` turns the
automatic shift off), `--no-word-times` keeps line times only (no
hearing, so it is faster), and `--no-lyrics` skips lyrics. riffkit prints which
source it used.

**Lyrics are for your own use.** riffkit fetches lyrics only for the
person running it, on their own machine, and never ships or publishes
them. Thanks to LRCLIB and its contributors for the timed lyrics.

### Using riffkit with an AI assistant

The easiest way to run riffkit may be to let an AI do it for you, but it
has to be the kind that can work on your computer.

* **Coding agents** such as Claude Code, Codex, Gemini CLI or Cursor run
  on your own machine and can install riffkit, run it and tell you where
  the project is. This repository includes `AGENTS.md`, instructions they
  read automatically. Open a terminal in the riffkit folder, start your
  agent and say something like:

  > Read the README. Install riffkit, then make a REAPER project from
  > `~/Music/My Song.wav`. Check my free memory first, and tell me
  > everything you run.

* **Chat assistants** in a browser (ChatGPT, Gemini or Claude on the web)
  can't run anything on your computer. They can still read this README
  with you and explain each command as you type it.

An AI makes the install and the commands easy. It can't make a slow
computer fast or rescue a poor recording: those still decide how good
the stems are.

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
* **It is slow on a CPU.** Expect about 11 minutes for a 4-minute
  song (stems and lyrics), and about 50 minutes to transcribe a 90-minute concert for
  setlist mode. The first run also downloads the lyrics model (about
  1.5 GB). It needs several GB of free memory (see Tested on).
* **Setlist mode is close, not perfect.** On the test concert it placed
  12 of 13 song starts and 12 of 13 song ends within a few seconds, and
  flagged the misses. Your own marks always override it.
* **Tested on Linux only.**

### Tested on

| | Linux | Windows | macOS |
| :--- | :--- | :--- | :--- |
| Status | Tested | In progress | Untested |
| Operating system | Ubuntu 26.04.1 LTS | Windows 10 (virtual machine) | — |
| Machine | AMD Ryzen 7 5700U (a low-power laptop processor in a small desktop), 14 GB of memory | 6 GB of memory | — |
| Python | 3.14.4 | 3.14 | — |
| REAPER | 7.45 | — | — |
| Key libraries | demucs 4.1.0, torch 2.15.0, faster-whisper 1.2.1, av 18.1.0 | — | — |
| One song (3 min 42 s) to a finished project | about 11 minutes (stems 8½, lyrics 2½) | — | — |
| Last tested | 2026-11-17 | — | — |

* A 90-minute concert transcript for setlist mode took 51 minutes (Linux).
* riffkit runs on the processor. A graphics card isn't used, and running
  with one hasn't been tried.
* Memory is the real limit: a run peaks at about 3.5 GB. With a browser
  open, runs have been killed for running out of memory. Close the
  browser first; allow 5 GB free to be safe.

### Regression testing

Every push runs the fast test suite (no audio, no models) on Linux,
Windows and macOS with GitHub Actions. Full runs on real audio take
minutes and several GB of memory, so they are done by hand, and only on
the platforms marked Tested above.

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
| `scripts/benchmark.py` | Times one song through the whole chain, checks the result and logs it to `data/benchmarks.csv`. |
| `lyrics-sync/` | Vocal transcription, transcript cleanup, REAPER lyrics scripts. |
| `stem-separation/` | Stem separation notes and the manual `import_stems.lua`. |
| `karaoke-display/` | A browser lyrics display synced to REAPER. |
| `docs/` | Use cases, roadmap, testing notes and step-by-step SOPs. |
| `AGENTS.md` | Instructions for AI coding agents running riffkit. |

### Philosophy

* **Built for me first.** Features arrive when I need them.
* **Shared without obligation.** Open source under the MIT license, with
  no support promises.
* **Modular.** Take the pieces you need.

*Historical note: this project was originally called Songster.*
