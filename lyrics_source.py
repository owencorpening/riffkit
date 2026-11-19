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


# --- Automatic offset ----------------------------------------------------------
#
# LRC timings are made for one copy of a recording; another upload of the same
# song can have a slightly longer or shorter lead-in, so every line is off by
# the same amount. Measure that against the vocals stem: near each line's
# start, find where the voice comes in, and take the median gap.

FRAME_SECONDS = 0.01
ONSET_WINDOW = (-0.6, 1.2)    # look this far before / after each line start
ONSET_HOLD_FRAMES = 5         # the voice must stay up for 50 ms
VOICE_BELOW_LOUD_DB = 25.0    # "voice" = within 25 dB of loud singing
MIN_ONSETS = 5                # need at least this many lines with a clear onset
MIN_ONSET_SHARE = 0.5         # ... and at least half of all lines
MAX_SPREAD = 0.6              # middle half of the gaps must fit in 0.6 s
MIN_OFFSET = 0.1              # smaller than this: leave the lyrics alone
MAX_OFFSET = 3.0              # larger than this: don't trust it


def frame_levels_db(samples, sample_rate: int) -> "np.ndarray":
    """RMS level in dB for consecutive 10 ms frames of a mono signal."""
    import numpy as np

    size = max(1, int(round(sample_rate * FRAME_SECONDS)))
    usable = len(samples) // size * size
    if usable == 0:
        return np.full(1, -120.0)
    frames = np.asarray(samples[:usable], dtype=np.float64).reshape(-1, size)
    return 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)


def voice_onsets(levels, starts: list[float]) -> list[float]:
    """Gap (voice start minus line start) for each line with a clear onset."""
    import numpy as np

    levels = np.asarray(levels, dtype=np.float64)
    threshold = np.percentile(levels, 90) - VOICE_BELOW_LOUD_DB
    hold = ONSET_HOLD_FRAMES
    gaps = []
    for start in starts:
        first = max(0, int(round((start + ONSET_WINDOW[0]) / FRAME_SECONDS)))
        last = min(len(levels), int(round((start + ONSET_WINDOW[1]) / FRAME_SECONDS)))
        window = levels[first:last]
        for i in range(hold, len(window) - hold):
            if (window[i:i + hold] > threshold).all() and (window[i - hold:i] <= threshold).any():
                gaps.append((first + i) * FRAME_SECONDS - start)
                break
    return gaps


def measure_offset(levels, segments: list[dict]) -> tuple[float | None, str]:
    """(offset to add to every line, or None; a note saying why).

    Returns an offset only when enough lines agree on it.
    """
    import numpy as np

    starts = [float(s["start"]) for s in segments]
    gaps = voice_onsets(levels, starts)
    used = f"{len(gaps)} of {len(starts)} lines"
    if len(gaps) < MIN_ONSETS or len(gaps) < MIN_ONSET_SHARE * len(starts):
        return None, f"too few clear voice starts ({used})"
    low, median, high = np.percentile(gaps, [25, 50, 75])
    if high - low > MAX_SPREAD:
        return None, f"lines disagree too much ({used}, middle half {low:+.2f} to {high:+.2f} s)"
    offset = round(float(median) / 0.05) * 0.05
    if abs(offset) < MIN_OFFSET:
        return None, f"already in time ({offset:+.2f} s, {used})"
    if abs(offset) > MAX_OFFSET:
        return None, f"measured {offset:+.2f} s, too large to trust ({used})"
    return offset, f"measured {offset:+.2f} s against the vocals ({used})"


def measure_offset_from_audio(vocals: Path, segments: list[dict]) -> tuple[float | None, str]:
    """measure_offset() on a vocals file, decoded to 16 kHz mono with ffmpeg."""
    import numpy as np

    sample_rate = 16000
    try:
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(vocals), "-ac", "1", "-ar", str(sample_rate),
             "-f", "f32le", "-"],
            capture_output=True,
        )
    except OSError as err:
        return None, f"could not read the vocals ({err})"
    if result.returncode != 0 or not result.stdout:
        return None, "could not read the vocals"
    try:
        samples = np.frombuffer(result.stdout, dtype=np.float32)
    except (TypeError, ValueError):
        return None, "could not read the vocals"
    return measure_offset(frame_levels_db(samples, sample_rate), segments)


# --- Word times for text lyrics -----------------------------------------------
#
# Lyrics from an .lrc file or LRCLIB have line times only. Whisper's heard
# words (from the vocals stem) carry word times but often the wrong words, so
# each line keeps its own words and borrows the heard times where the words
# match, using the same normalising and matching as scripts/compare_lyrics.py.

WORD_SLACK = 0.5      # heard words this far outside a line still count for it
MIN_WORD_GAP = 0.01   # each word starts at least this long after the one before

_WORD_RE = re.compile(r"[\w']+")


def normalize(text: str) -> list[str]:
    """Lowercase words with punctuation removed (as in scripts/compare_lyrics.py)."""
    words = []
    for token in _WORD_RE.findall(text.lower()):
        token = token.strip("'")
        if token:
            words.append(token)
    return words


def heard_words(doc: dict) -> list[tuple[float, str]]:
    """(start, word) for every timed word in a heard transcript, by time."""
    words = []
    for seg in doc.get("segments") or []:
        for w in seg.get("words") or []:
            if w.get("start") is not None and str(w.get("word", "")).strip():
                words.append((float(w["start"]), str(w["word"])))
    words.sort(key=lambda w: w[0])
    return words


def _spread(lengths: list[int], start: float, end: float) -> list[float]:
    """Start times for words sharing [start, end] in proportion to their length."""
    total = sum(lengths) or 1
    times, done = [], 0
    for n in lengths:
        times.append(start + (end - start) * done / total)
        done += n
    return times


def time_line_words(line: dict, heard: list[tuple[float, str]]) -> tuple[list[dict], int]:
    """(words with start times, how many of them took a heard time) for one line."""
    import difflib

    words = line["text"].split()
    if not words:
        return [], 0
    start, end = float(line["start"]), float(line["end"])
    end = max(end, start)

    # Normalised tokens of the line's words, each remembering its word.
    tokens, owner = [], []
    for i, w in enumerate(words):
        for t in normalize(w):
            tokens.append(t)
            owner.append(i)
    near = [(t, w) for t, w in heard if start - WORD_SLACK <= t <= end + WORD_SLACK]
    heard_tokens, heard_times = [], []
    for t, w in near:
        for tok in normalize(w):
            heard_tokens.append(tok)
            heard_times.append(t)

    times: list[float | None] = [None] * len(words)
    matcher = difflib.SequenceMatcher(None, tokens, heard_tokens, autojunk=False)
    for tag, i1, i2, j1, _ in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                i = owner[i1 + k]
                if times[i] is None:
                    times[i] = min(max(heard_times[j1 + k], start), end)
    matched = sum(t is not None for t in times)

    lengths = [max(1, len("".join(normalize(w)))) for w in words]
    if matched == 0:
        step = (end - start) / len(words)
        times = [start + step * i for i in range(len(words))]
    else:
        anchors = [i for i, t in enumerate(times) if t is not None]
        # Words before the first match share [line start, first match].
        first = anchors[0]
        if first:
            times[:first] = _spread(lengths[:first], start, times[first])
        # Words after a match share its slot with it, up to the next match
        # (or the line's end).
        for a, b in zip(anchors, anchors[1:] + [len(words)]):
            if b - a > 1:
                stop = times[b] if b < len(words) else end
                stop = max(stop, times[a])
                times[a:b] = [times[a]] + _spread(lengths[a:b], times[a], stop)[1:]

    for i in range(1, len(times)):
        times[i] = max(times[i], times[i - 1] + MIN_WORD_GAP)
    times = [round(t, 3) for t in times]
    return [{"word": " " + w, "start": t} for w, t in zip(words, times)], matched


def add_word_times(segments: list[dict], heard: list[tuple[float, str]]) -> tuple[list[dict], int, int]:
    """(segments with words[], words with heard times, words spread) for text lyrics."""
    out, matched, spread = [], 0, 0
    for seg in segments:
        words, n = time_line_words(seg, heard)
        out.append({**seg, "words": words})
        matched += n
        spread += len(words) - n
    return out, matched, spread
