# Personal Library Convention

This repo keeps the tooling.
Your actual concert library should live outside the repo, for example under `~/Music/riffkit-library`.

## Goals

- Preserve provenance for every concert.
- Keep the visible folder names sortable.
- Keep the original source title and URL attached to the concert, not hidden in the folder name.
- Store one song per folder so the REAPER project can live beside the extracted audio.

## Recommended Layout

```text
~/Music/riffkit-library/
  concerts/
    1970-04-26 - Jimi Hendrix - Live in Stockholm (1970)/
      provenance.json
      source/
        concert.txt
        segments.json
      songs/
        01 - Introduction/
          audio.mp3
          project.rpp
        02 - Fire Part 1/
          audio.mp3
          project.rpp
```

## Provenance

Keep the original title, URL, and any other source details in `provenance.json`.
At minimum, capture:

- original source title
- source URL
- retrieval date
- date of the concert, if known
- artist name
- any source file hashes you can compute

## Folder Naming

Use an ISO-like date prefix so the library sorts naturally:

`YYYY-MM-DD - Artist - Concert Title`

If the exact day is unknown, use the best date you have and document the uncertainty in `provenance.json`.

## Song Folders

Each song gets its own folder under `songs/`.
That folder is where the extracted audio and the eventual REAPER project belong.

This keeps one song self-contained and makes it easier to add stems, notes, or alternate exports later.
