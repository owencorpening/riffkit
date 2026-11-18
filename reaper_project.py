#!/usr/bin/env python3
"""
Write a REAPER project (.RPP) with a song's stems already on their tracks.

REAPER project files are plain text, so riffkit can write one directly
instead of copying an empty template and asking the user to import the
stems by hand. The result opens with:

    Vocals, Drums, Bass, Other   one stem each, at the song's start
    Original                     the unseparated song, muted
    Lyrics                       one text item per sung line, if a
                                 transcript is given

Paths inside the project are relative to the .RPP file, so the folder can
be moved or zipped as a whole.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path

STEM_TRACKS = [
    ("Vocals", ("vocals", "vocal", "vox")),
    ("Drums", ("drums", "drum", "percussion")),
    ("Bass", ("bass",)),
    ("Other", ("other", "guitar", "keys", "piano", "melody")),
]
AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".aiff", ".ogg"}
MIN_LYRIC_SECONDS = 0.1
_SOURCE_TYPE = {".wav": "WAVE", ".mp3": "MP3", ".flac": "FLAC", ".aiff": "WAVE", ".ogg": "VORBIS"}


def _guid() -> str:
    return "{" + str(uuid.uuid4()).upper() + "}"


def _escape(text: str) -> str:
    return text.replace('"', "'")


def match_stem_files(stems_dir: Path) -> dict[str, Path]:
    """Map track names to stem files found in ``stems_dir``.

    Matches on words in the file name, first track to match wins, so a file
    called ``bass.wav`` lands on Bass and ``other.wav`` on Other.
    """
    found: dict[str, Path] = {}
    for path in sorted(Path(stems_dir).iterdir()):
        if path.suffix.lower() not in AUDIO_SUFFIXES:
            continue
        stem = path.stem.lower()
        for track, keywords in STEM_TRACKS:
            if track in found:
                continue
            if any(word in stem for word in keywords):
                found[track] = path
                break
    return found


def media_duration(audio_file: Path) -> float:
    """Length in seconds via ffprobe; 0.0 if ffprobe is unavailable."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(audio_file)],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())
    except (OSError, subprocess.CalledProcessError, ValueError):
        return 0.0


def _track_block(name: str, media: Path | None, project_dir: Path, length: float,
                 muted: bool = False) -> str:
    """One <TRACK> block, with one item on it if ``media`` is given."""
    lines = [
        "  <TRACK " + _guid(),
        f'    NAME "{_escape(name)}"',
        "    TRACKID " + _guid(),
        f"    MUTESOLO {1 if muted else 0} 0 0",
        "    VOLPAN 1 0 -1 -1 1",
    ]
    if media is not None:
        try:
            rel = Path(os.path.relpath(media, project_dir)).as_posix()
        except ValueError:  # Windows: media and project on different drives
            rel = Path(os.path.abspath(media)).as_posix()
        source_type = _SOURCE_TYPE.get(media.suffix.lower(), "WAVE")
        lines += [
            "    <ITEM",
            "      POSITION 0",
            "      IGUID " + _guid(),
            "      GUID " + _guid(),
            f"      LENGTH {length:.6f}",
            f'      NAME "{_escape(media.name)}"',
            "      VOLPAN 1 0 1 -1",
            f"      <SOURCE {source_type}",
            f'        FILE "{_escape(rel)}"',
            "      >",
            "    >",
        ]
    lines.append("  >")
    return "\n".join(lines)


def playable_original(original: Path, project_dir: Path) -> Path:
    """Return a file REAPER can play for the Original track.

    Formats REAPER reads from a project's SOURCE tag (wav, mp3, flac, aiff,
    ogg) are used where they are. Anything else (opus, m4a, ...) is decoded
    once to ``original.wav`` beside the project; given the wrong SOURCE type
    REAPER shows an empty, silent item. The copy also keeps the song folder
    self-contained.
    """
    original = Path(original)
    if original.suffix.lower() in _SOURCE_TYPE:
        return original
    converted = Path(project_dir) / "original.wav"
    if not converted.exists():
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(original), str(converted)],
            check=True,
        )
    return converted


def load_lyrics(transcript_file: Path) -> list[dict]:
    """Segments from a Whisper-style transcript JSON (``{"segments": [...]}``)."""
    doc = json.loads(Path(transcript_file).read_text(encoding="utf-8"))
    return list(doc.get("segments") or [])


def _lyrics_track_block(segments: list[dict]) -> str:
    """A track named Lyrics with one empty item per line, text in its notes.

    REAPER shows an empty item's notes as text on the item, so the lyrics
    are readable on the timeline with no script or extension.
    """
    lines = [
        "  <TRACK " + _guid(),
        '    NAME "Lyrics"',
        "    TRACKID " + _guid(),
        "    MUTESOLO 0 0 0",
        "    VOLPAN 1 0 -1 -1 1",
    ]
    for seg in segments:
        text = " ".join(str(seg.get("text", "")).split())
        if not text:
            continue
        start = float(seg["start"])
        length = max(MIN_LYRIC_SECONDS, float(seg["end"]) - start)
        lines += [
            "    <ITEM",
            f"      POSITION {start:.3f}",
            f"      LENGTH {length:.3f}",
            "      IGUID " + _guid(),
            "      GUID " + _guid(),
            "      <NOTES",
            f"        |{text}",
            "      >",
            "    >",
        ]
    lines.append("  >")
    return "\n".join(lines)


def write_reaper_project(
    project_file: Path,
    stems_dir: Path,
    original: Path | None = None,
    length_seconds: float | None = None,
    lyrics: list[dict] | None = None,
) -> Path:
    """Write ``project_file`` with the stems in ``stems_dir`` on named tracks.

    ``original`` is the unseparated song; it goes on a muted fifth track.
    ``length_seconds`` is the item length; measured from the first stem when
    not given. ``lyrics`` is a list of transcript segments (start, end,
    text); they go on a last track named Lyrics. Raises FileNotFoundError if
    no stem files are found.
    """
    project_file = Path(project_file)
    stems_dir = Path(stems_dir)
    stems = match_stem_files(stems_dir)
    if not stems:
        raise FileNotFoundError(f"No stem files found in {stems_dir}")

    if length_seconds is None:
        length_seconds = media_duration(next(iter(stems.values())))
    project_dir = project_file.parent.resolve()

    blocks = [
        _track_block(track, stems.get(track), project_dir, length_seconds)
        for track, _ in STEM_TRACKS
    ]
    if original is not None:
        original = playable_original(Path(original).resolve(), project_dir)
        blocks.append(_track_block("Original", original, project_dir,
                                   length_seconds, muted=True))
    if lyrics:
        blocks.append(_lyrics_track_block(lyrics))

    text = "\n".join([
        "<REAPER_PROJECT 0.1 \"7.0\" 0",
        "  RIPPLE 0",
        "  GROUPOVERRIDE 0 0 0",
        "  AUTOXFADE 129",
        "  SAMPLERATE 48000 0 0",
        "  TEMPO 120 4 4",
        "  TIMELOCKMODE 0",
        "  CURSOR 0",
        "  ZOOM 100 0 0",
        *blocks,
        ">",
        "",
    ])
    project_file.parent.mkdir(parents=True, exist_ok=True)
    project_file.write_text(text, encoding="utf-8")
    return project_file
