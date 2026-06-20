# riffkit Use Cases

## 1. Church Band Set Prep

### Who it is for

A small church band that receives a short set of songs ahead of time and needs to be ready for rehearsal and service.

### Inputs

* 3-4 MP3 or WAV files
* A performance date
* Optional lyric source or Whisper transcription output

### Outputs

* Separated stems for each song
* One REAPER project per song, typically with up to about five parts to manage
* Lyrics for rehearsal or a large-screen display

### What riffkit does

* Separates the songs into stems
* Lets each player mute their own part and learn the rest
* Imports or displays lyrics
* Keeps each song organized in its own REAPER project

### Relevant files

* `riftkit.py`
* `stem-separation/import_stems.lua`
* `lyrics-sync/InsertLyrics.lua`
* `lyrics-sync/AddLyrics.lua`
* `scripts/reaper/live_lyric_viewer.lua`

## 2. Personal Part Learning

### Who it is for

A single musician who wants to practice one part of a song without losing the context of the full arrangement.

### Inputs

* One song file
* A target part: drums, bass, guitar, vocals, or keyboards

### Outputs

* Stem-separated practice audio
* A REAPER project with the right track layout, one project per song

### What riffkit does

* Splits the track into usable stems
* Makes it easy to mute the part you are learning
* Lets you slow down or rehearse with the rest of the band still present

### Relevant files

* `riftkit.py`
* `stem-separation/README.md`
* `stem-separation/import_stems.lua`
* `scripts/reaper/quick_master_bus_toggle.lua`

## 3. Concert Ingestion

### Who it is for

A band, church team, or engineer who has a long concert recording and needs to split it into individual songs before doing anything else.

### Inputs

* One long MP3 or WAV recording
* A rough silence pattern between songs
* Optional sidecar text file with song titles in order

### Outputs

* One file per song
* A segments manifest with timing information
* Optional song names pulled from the sidecar text file

### What riffkit does

* Detects long silence gaps
* Splits the recording into song-sized files
* Keeps the output ready for the normal stem / lyric / REAPER workflow

### Relevant files

* `riftkit.py`

## 4. Live Performance With Lyrics

### Who it is for

A band or performer who needs playback, lyrics, and stage cues during a live set.

### Inputs

* A REAPER project
* Markers or lyrics
* Optional MIDI/OSC control setup

### Outputs

* Synchronized lyric display
* Stage cue handling
* Optional remote control behavior

### What riffkit does

* Displays lyrics in a large readable window
* Triggers lighting or stage cues from timeline markers
* Accepts remote-control style input for performance use

### Relevant files

* `scripts/reaper/live_lyric_viewer.lua`
* `scripts/reaper/stage_lighting_sync.lua`
* `scripts/reaper/smart_midi_remote.lua`

## Notes

These are the main use cases the repo is currently organized around. New features should generally support one of these workflows.
