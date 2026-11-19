"""
Where a song's lyrics come from, in this order (``--lyrics-from auto``):

1. A ``.lrc`` file next to the song with the same name ("Song.lrc").
2. LRCLIB (https://lrclib.net): one lookup by artist, title and the song's
   duration. Only a result with synced (timed) lyrics whose duration is
   within 2 s of the file's is used. It is saved as "Song.lrc" next to the
   song, so it is never fetched twice.
3. Otherwise riffkit hears the lyrics: Whisper transcribes the vocals stem.

Lyrics are fetched for the user's own use only; riffkit never ships them.

LRC lines become riffkit's lyrics.json segments: one segment per line,
ending where the next line begins. Empty lines (end markers) only end the
line before them.
"""

from __future__ import annotations

import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

LRCLIB_GET = "https://lrclib.net/api/get"
DURATION_TOLERANCE = 2.0  # seconds between LRCLIB's duration and the file's
LAST_LINE_SECONDS = 4.0   # length of the last line when nothing ends it
USER_AGENT = "riffkit (lyrics lookup)"
SOURCES = ("auto", "lrc", "lrclib", "hear")

_TIMESTAMP_RE = re.compile(r"\[(\d+):(\d{1,2}(?:[.:]\d{1,3})?)\]")


def parse_lrc(text: str) -> list[tuple[float, str]]:
    """(seconds, text) for every timestamped line, sorted by time.

    Handles several timestamps on one line ("[00:12.00][00:45.00]text") and
    ignores tag lines such as "[ar:Artist]". Empty text is kept: it marks
    where the line before it ends.
    """
    entries = []
    for raw in text.splitlines():
        stamps = []
        rest = raw.strip()
        while True:
            m = _TIMESTAMP_RE.match(rest)
            if not m:
                break
            seconds = m[2].replace(":", ".")
            stamps.append(int(m[1]) * 60 + float(seconds))
            rest = rest[m.end():]
        for t in stamps:
            entries.append((t, rest.strip()))
    entries.sort(key=lambda e: e[0])
    return entries


def lrc_to_segments(text: str, last_end: float | None = None) -> list[dict]:
    """LRC text to riffkit lyrics segments (start, end, text, no words).

    Each sung line ends where the next timestamp begins (an empty end marker
    counts). The last line ends at ``last_end`` (the song's length) if given,
    otherwise LAST_LINE_SECONDS after it starts.
    """
    entries = parse_lrc(text)
    segments = []
    for i, (start, line) in enumerate(entries):
        if not line:
            continue
        if i + 1 < len(entries):
            end = entries[i + 1][0]
        else:
            end = last_end if last_end and last_end > start else start + LAST_LINE_SECONDS
        segments.append({"id": len(segments), "start": start, "end": end,
                         "text": " " + line, "words": []})
    return segments


def shift_segments(segments: list[dict], offset: float) -> list[dict]:
    """Move every line (and word) by ``offset`` seconds, never before 0."""
    if not offset:
        return segments
    shifted = []
    for seg in segments:
        seg = dict(seg)
        seg["start"] = max(0.0, float(seg["start"]) + offset)
        seg["end"] = max(seg["start"], float(seg["end"]) + offset)
        if seg.get("words"):
            seg["words"] = [
                {**w, **{k: max(0.0, float(w[k]) + offset) for k in ("start", "end") if k in w}}
                for w in seg["words"]
            ]
        shifted.append(seg)
    return shifted


def read_tags(audio_file: Path) -> tuple[str | None, str | None]:
    """(artist, title) from the file's tags via ffprobe, or None for each."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format_tags:stream_tags",
             "-of", "json", str(audio_file)],
            capture_output=True, text=True,
        )
        doc = json.loads(result.stdout)
    except (OSError, TypeError, ValueError):
        return None, None
    if not isinstance(doc, dict):
        return None, None
    tags: dict[str, str] = {}
    sources = [doc.get("format", {}).get("tags", {})]
    sources += [s.get("tags", {}) for s in doc.get("streams", [])]
    for source in sources:
        for key, value in (source or {}).items():
            tags.setdefault(str(key).lower(), str(value).strip())
    return tags.get("artist") or None, tags.get("title") or None


def _http_get(url: str, timeout: float = 15.0) -> tuple[int, str]:
    """(status, body) for a GET. The only place riffkit touches the network."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        return err.code, ""


def fetch_lrclib(artist: str, title: str, duration: float) -> str | None:
    """Synced LRC text from LRCLIB, or None. Exactly one request."""
    query = urllib.parse.urlencode({
        "artist_name": artist,
        "track_name": title,
        "duration": round(duration),
    })
    try:
        status, body = _http_get(f"{LRCLIB_GET}?{query}")
    except (OSError, ValueError):
        return None
    if status != 200:
        return None
    try:
        doc = json.loads(body)
    except ValueError:
        return None
    synced = doc.get("syncedLyrics") if isinstance(doc, dict) else None
    found = doc.get("duration") if isinstance(doc, dict) else None
    if not synced or found is None:
        return None
    if abs(float(found) - duration) > DURATION_TOLERANCE:
        return None
    return synced


def find_lyrics(
    audio_file: Path,
    source: str = "auto",
    artist: str | None = None,
    title: str | None = None,
    duration: float | None = None,
) -> tuple[list[dict] | None, str]:
    """Lyrics segments from an .lrc file or LRCLIB, and a note on the source.

    Returns (None, note) when the caller should hear the lyrics instead (or,
    for an explicit source that found nothing, skip them). ``duration`` is
    only needed for LRCLIB and for ending the last line.
    """
    lrc_file = audio_file.with_suffix(".lrc")

    if source in ("auto", "lrc"):
        if lrc_file.exists():
            segments = lrc_to_segments(lrc_file.read_text(encoding="utf-8"), duration)
            if segments:
                return segments, f".lrc file next to the song ({lrc_file.name})"
            if source == "lrc":
                return None, f"{lrc_file.name} has no timed lines"
        elif source == "lrc":
            return None, f"no .lrc file next to the song ({lrc_file.name})"

    if source in ("auto", "lrclib"):
        if not artist or not title:
            note = "LRCLIB skipped: no artist and title (use --artist and --title)"
        elif not duration:
            note = "LRCLIB skipped: the song's duration is unknown"
        else:
            synced = fetch_lrclib(artist, title, duration)
            if synced:
                segments = lrc_to_segments(synced, duration)
                if segments:
                    if not lrc_file.exists():
                        lrc_file.write_text(synced, encoding="utf-8")
                    return segments, f"LRCLIB ({artist} - {title}), saved as {lrc_file.name}"
            note = f"LRCLIB has no synced lyrics within {DURATION_TOLERANCE:g} s of this file"
        return None, note

    return None, "hearing the lyrics was requested"
