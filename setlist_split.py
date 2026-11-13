#!/usr/bin/env python3
"""
Setlist-mode concert splitting for riftkit.

Pause detection (riftkit.detect_silence_intervals) needs a long, near-silent
gap between songs. Live shows rarely give it one: the breaks are full of crowd
noise, tuning and stage talk, and some songs run straight into the next.

Setlist mode uses the one thing pause detection ignores: we already know how
many songs there are and what they are called.

    1. Breaks      - find every stretch where the band drops out, however
                     briefly, from the level curve of the recording.
    2. Anchors     - find where each setlist title is sung or announced in a
                     Whisper transcript ("song N is playing at time T").
    3. Selection   - choose exactly one boundary per song, in setlist order,
                     so that the strongest breaks are used and every anchor
                     falls inside its own song.

Only numpy and ffmpeg are required for steps 1 and 3. Step 2 needs a Whisper
JSON transcript with word timestamps (see docs/sops/local-transcription.md).
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ANALYSIS_SAMPLE_RATE = 11025
LEVEL_HOP_SECONDS = 0.1


# ---------------------------------------------------------------------------
# Setlist parsing
# ---------------------------------------------------------------------------

_HEADER_PREFIXES = ("date:", "venue:", "source:", "concert:", "artist:", "notes:")
_SETLIST_HEADER_RE = re.compile(r"^(set\s?list|songs)\b.*:\s*$", re.IGNORECASE)
_NUMBERED_LINE_RE = re.compile(r"^\s*(\d+)\s*[\).\-:]\s*(\S.*)$")


_SKIP_LINE_RE = re.compile(r"^\s*(?:[-*]\s*)?(\(.+\))\s*$")


def is_skip_entry(title: str) -> bool:
    """A setlist entry written wholly in parentheses, such as "(solo)".

    It marks music that sits between songs but is not one of them. Setlist
    mode finds where it starts and ends like any song, then writes no file.
    """
    title = title.strip()
    return title.startswith("(") and title.endswith(")")


def parse_setlist(setlist_file: Path) -> list[str]:
    """Return the setlist entries, in order, from a setlist text file.

    Accepted layouts:
      * numbered lines ("1. Spanish Castle Magic") anywhere in the file
      * plain titles, one per line, after a "Setlist:" / "Songs:" header line
      * plain titles, one per line, with no header at all

    A line wholly in parentheses, such as "(solo)", is a skip entry (see
    is_skip_entry) and is kept in its place whichever layout is used.

    Lines such as "Date:", "Venue:" and "Source:" are ignored, and so is any
    free text above a setlist header (for example the concert name).
    """
    lines = Path(setlist_file).read_text(encoding="utf-8").splitlines()

    ordered: list[str] = []
    numbered_found = False
    for line in lines:
        numbered = _NUMBERED_LINE_RE.match(line)
        skip = _SKIP_LINE_RE.match(line)
        if numbered:
            numbered_found = True
            ordered.append(numbered.group(2).strip())
        elif skip:
            ordered.append(skip.group(1).strip())
    if numbered_found:
        return ordered

    header_index = next(
        (i for i, line in enumerate(lines) if _SETLIST_HEADER_RE.match(line.strip())),
        None,
    )
    body = lines[header_index + 1 :] if header_index is not None else lines
    titles = []
    for raw in body:
        line = raw.strip().lstrip("-* ").strip() if _SKIP_LINE_RE.match(raw) else raw.strip()
        if not line or line.lower().startswith(_HEADER_PREFIXES):
            continue
        titles.append(line)
    return titles


# ---------------------------------------------------------------------------
# Level curve
# ---------------------------------------------------------------------------

def load_mono_audio(audio_file: Path, sample_rate: int = ANALYSIS_SAMPLE_RATE):
    """Decode any ffmpeg-readable file to a mono float32 numpy array."""
    import numpy as np

    result = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", str(audio_file),
            "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "-",
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg could not decode {Path(audio_file).name}: "
            f"{result.stderr.decode(errors='replace').strip()}"
        )
    return np.frombuffer(result.stdout, dtype=np.float32)


def level_curve(samples, sample_rate: int = ANALYSIS_SAMPLE_RATE,
                hop_seconds: float = LEVEL_HOP_SECONDS):
    """RMS level in dB, one value per hop."""
    import numpy as np

    hop = max(1, int(round(sample_rate * hop_seconds)))
    frames = len(samples) // hop
    if frames == 0:
        return np.zeros(0, dtype=np.float32)
    blocks = np.asarray(samples[: frames * hop], dtype=np.float32).reshape(frames, hop)
    rms = np.sqrt((blocks ** 2).mean(axis=1) + 1e-12)
    return 20.0 * np.log10(rms)


def _smooth(values, width: int):
    import numpy as np

    if width <= 1 or len(values) == 0:
        return np.asarray(values, dtype=np.float64)
    padded = np.pad(np.asarray(values, dtype=np.float64), (width // 2, width - 1 - width // 2), mode="edge")
    return np.convolve(padded, np.ones(width) / width, mode="valid")


# ---------------------------------------------------------------------------
# Tone features (one row per second)
# ---------------------------------------------------------------------------

def tone_features(samples, sample_rate: int = ANALYSIS_SAMPLE_RATE):
    """Per-second pitch-class profile and tone balance.

    Returns (chroma, shares):
      chroma  (seconds, 12)  which notes are sounding, normalised to sum to 1
      shares  (seconds, 5)   how the energy is spread from bass to treble

    Chroma tells songs in different keys apart. Shares tell textures apart
    (full band against a guitar on its own, for example).
    """
    import numpy as np

    frame = 2048
    hop = 1024
    count = (len(samples) - frame) // hop
    seconds = int(len(samples) / sample_rate)
    if count <= 0 or seconds <= 0:
        return np.zeros((0, 12)), np.zeros((0, 5))

    freqs = np.fft.rfftfreq(frame, 1.0 / sample_rate)
    window = np.hanning(frame).astype(np.float32)
    pitch_class = np.round(12 * np.log2(np.maximum(freqs, 1.0) / 440.0) + 69).astype(int) % 12
    tonal_range = (freqs > 80) & (freqs < 2000)
    chroma_masks = [tonal_range & (pitch_class == k) for k in range(12)]
    edges = np.geomspace(60, 5000, 6)
    share_masks = [(freqs >= lo) & (freqs < hi) for lo, hi in zip(edges[:-1], edges[1:])]

    chroma = np.zeros((count, 12), dtype=np.float64)
    shares = np.zeros((count, 5), dtype=np.float64)
    block = 2000
    for start in range(0, count, block):
        stop = min(count, start + block)
        index = np.arange(start, stop)[:, None] * hop + np.arange(frame)[None, :]
        power = np.abs(np.fft.rfft(samples[index] * window, axis=1)) ** 2
        for k, mask in enumerate(chroma_masks):
            chroma[start:stop, k] = power[:, mask].sum(axis=1)
        for k, mask in enumerate(share_masks):
            shares[start:stop, k] = power[:, mask].sum(axis=1)

    frame_second = (np.arange(count) * hop / sample_rate).astype(int)
    keep = frame_second < seconds

    def per_second(values):
        out = np.zeros((seconds, values.shape[1]))
        np.add.at(out, frame_second[keep], values[keep])
        return out / (out.sum(axis=1, keepdims=True) + 1e-12)

    return per_second(chroma), per_second(shares)


# ---------------------------------------------------------------------------
# Beat
# ---------------------------------------------------------------------------

def beat_strength(samples, sample_rate: int = ANALYSIS_SAMPLE_RATE, window_seconds: float = 8.0):
    """How clear a steady beat is, one value (0..1) per second.

    Note onsets are found from sudden rises in the spectrum. For each second,
    the onsets in the surrounding ``window_seconds`` are compared with
    themselves shifted by every beat length from 60 to 200 beats per minute.
    A band playing in time repeats strongly at its beat length; free playing,
    feedback, talk and applause do not.
    """
    import numpy as np

    frame = 1024
    hop = 256
    count = (len(samples) - frame) // hop
    seconds = int(len(samples) / sample_rate)
    if count <= 0 or seconds <= 0:
        return np.zeros(0)
    window = np.hanning(frame).astype(np.float32)
    onsets = np.zeros(count, dtype=np.float32)
    previous = None
    block = 4000
    for start in range(0, count, block):
        stop = min(count, start + block)
        index = np.arange(start, stop)[:, None] * hop + np.arange(frame)[None, :]
        spectrum = np.log1p(50.0 * np.abs(np.fft.rfft(samples[index] * window, axis=1)))
        rise = np.diff(np.vstack([previous if previous is not None else spectrum[:1], spectrum]), axis=0)
        onsets[start:stop] = np.maximum(0.0, rise).sum(axis=1)
        previous = spectrum[-1:]

    rate = sample_rate / hop
    half = int(window_seconds / 2 * rate)
    shortest = int(0.30 * rate)   # 200 beats per minute
    longest = int(1.00 * rate)    # 60 beats per minute
    strength = np.zeros(seconds)
    for second in range(seconds):
        centre = int(second * rate)
        if centre - half < 0 or centre + half > count:
            continue
        piece = onsets[centre - half:centre + half].astype(np.float64)
        piece -= piece.mean()
        repeat = np.correlate(piece, piece, "full")[len(piece) - 1:]
        if repeat[0] <= 0:
            continue
        strength[second] = float(repeat[shortest:longest].max() / repeat[0])
    return strength


def find_beat_starts(strength, window_seconds: int = 60, clear: float = 0.25,
                     min_rise: float = 0.4, spacing_seconds: int = 40) -> list["Break"]:
    """Find where a steady beat sets in and stays.

    Compares the share of seconds with a clear beat in the minute after each
    point with the minute before it. A song that follows free playing shows a
    large, lasting rise; a drum fill or a short break inside a song does not.
    """
    import numpy as np

    strength = np.asarray(strength, dtype=np.float64)
    n = len(strength)
    w = window_seconds
    if n < 2 * w + 1:
        return []
    total = np.concatenate(([0.0], np.cumsum((strength > clear).astype(np.float64))))
    rise = np.zeros(n)
    index = np.arange(w, n - w)
    rise[index] = (total[index + w] - total[index]) / w - (total[index] - total[index - w]) / w

    out = []
    for t in range(w, n - w):
        lo, hi = max(0, t - spacing_seconds), min(n, t + spacing_seconds + 1)
        if rise[t] >= min_rise and rise[t] == rise[lo:hi].max() and rise[t] > rise[t - 1]:
            out.append(Break(
                start=float(t), end=float(t), depth_db=0.0, quiet_seconds=0.0,
                cut=float(t), score=0.8 * min(1.0, float(rise[t])), kind="beat",
            ))
    return out


# ---------------------------------------------------------------------------
# Breaks
# ---------------------------------------------------------------------------

@dataclass
class Break:
    """A place where one song could end and the next begin.

    kind          "break"   the band drops out (deep dip in level)
                  "lull"    the level sags without really stopping
                  "change"  no drop in level, but the tone balance shifts
                  "beat"    no drop in level, but a steady beat sets in
    start / end   seconds, the whole stretch (a break is usually several dips
                  with applause, talk or tuning between them)
    cut           where the next song starts if this candidate is chosen
    music_stop    where the song before it stops (the first dip of a break).
                  None for a change: the two songs meet at the cut.
    score         0..1, how convincing it is on its own
    """

    start: float
    end: float
    depth_db: float
    quiet_seconds: float
    cut: float = 0.0
    score: float = 0.0
    kind: str = "break"
    music_stop: float | None = None

    def stop(self) -> float:
        """Where the song before this candidate ends."""
        return self.cut if self.music_stop is None else min(self.music_stop, self.cut)


def _dips(smoothed, reference: float, drop_db: float, hop_seconds: float,
          min_seconds: float) -> list[tuple[float, float, float]]:
    """(start, end, depth_db) for every run below reference - drop_db."""
    import numpy as np

    quiet = smoothed < (reference - drop_db)
    edges = np.diff(np.concatenate(([0], quiet.astype(np.int8), [0])))
    out = []
    for s, e in zip(np.where(edges == 1)[0], np.where(edges == -1)[0]):
        if (e - s) * hop_seconds >= min_seconds:
            out.append((s * hop_seconds, e * hop_seconds, reference - float(smoothed[s:e].min())))
    return out


def _cluster(dips, island_seconds: float) -> list[list[tuple[float, float, float]]]:
    clusters: list[list[tuple[float, float, float]]] = []
    for dip in dips:
        if clusters and dip[0] - clusters[-1][-1][1] < island_seconds:
            clusters[-1].append(dip)
        else:
            clusters.append([dip])
    return clusters


def find_breaks(
    level_db,
    hop_seconds: float = LEVEL_HOP_SECONDS,
    drop_db: float = 10.0,
    lull_drop_db: float = 5.0,
    min_quiet_seconds: float = 2.0,
    island_seconds: float = 15.0,
    preroll_seconds: float = 4.5,
    reset_margin_db: float = 3.0,
    flourish_seconds: float = 5.0,
    flourish_margin_db: float = 3.0,
    smooth_seconds: float = 0.5,
) -> list[Break]:
    """Find breaks and lulls in the level curve.

    A dip is any stretch at least ``drop_db`` quieter than the median level of
    the whole recording. Dips with less than ``island_seconds`` of sound
    between them are one break: nothing that short is a song, so it is
    applause, talk, tuning or a count-in.

    Inside a break, the cut goes at the deepest dip, which is where the stage
    actually falls quiet before the next song. If several dips are within
    ``reset_margin_db`` of the deepest, the last of them is used. The next
    song starts ``preroll_seconds`` before that dip ends, so a count-in or
    pickup is not clipped, but never before the break itself starts. The
    song before it stops where the break's first dip begins.

    One exception: if the band comes back at full volume for at least
    ``flourish_seconds`` and then stops again, that was the end of the song
    before, so only the dips after it are considered.

    Lulls use the gentler ``lull_drop_db`` threshold and are only reported
    where no break was found; they score half as much.
    """
    import numpy as np

    level = np.asarray(level_db, dtype=np.float64)
    if len(level) == 0:
        return []
    smoothed = _smooth(level, max(1, int(round(smooth_seconds / hop_seconds))))
    reference = float(np.median(smoothed))

    def build(clusters, kind: str, scale: float) -> list[Break]:
        out = []
        for dips in clusters:
            quiet_seconds = sum(e - s for s, e, _ in dips)
            if quiet_seconds < min_quiet_seconds:
                continue
            # A burst of full-volume playing shorter than a song, with a dip
            # on each side, is the last flourish of the song that is ending.
            # Only dips after the last such burst can start the next song.
            live = dips
            floor = dips[0][0]
            for i in range(len(dips) - 1):
                a = int(round(dips[i][1] / hop_seconds))
                b = int(round(dips[i + 1][0] / hop_seconds))
                if (b - a) * hop_seconds >= flourish_seconds and \
                        float(smoothed[a:b].mean()) >= reference - flourish_margin_db:
                    live = dips[i + 1:]
                    floor = dips[i][1]
            deepest = max(d for _, _, d in live)
            reset = [dip for dip in live if dip[2] >= deepest - reset_margin_db][-1]
            brk = Break(
                start=dips[0][0],
                end=dips[-1][1],
                depth_db=deepest,
                quiet_seconds=quiet_seconds,
                cut=max(floor, reset[1] - preroll_seconds),
                kind=kind,
                music_stop=dips[0][0],
            )
            brk.score = scale * break_score(brk)
            out.append(brk)
        return out

    breaks = build(_cluster(_dips(smoothed, reference, drop_db, hop_seconds, 0.5), island_seconds), "break", 1.0)
    lulls = build(_cluster(_dips(smoothed, reference, lull_drop_db, hop_seconds, 0.5), 3.0), "lull", 0.5)
    lulls = [l for l in lulls if not any(b.start - 1.0 <= l.end and l.start <= b.end + 1.0 for b in breaks)]
    return sorted(breaks + lulls, key=lambda b: b.cut)


def break_score(brk: Break) -> float:
    """0..1: longer and deeper breaks are more likely to separate two songs."""
    length = min(1.0, brk.quiet_seconds / 6.0)
    depth = min(1.0, brk.depth_db / 25.0)
    return 0.5 * length + 0.5 * depth


def find_changes(shares, window_seconds: int = 6, spacing_seconds: int = 15,
                 min_change: float = 0.35) -> list[Break]:
    """Find places where the tone balance shifts with no drop in level.

    This is what a song running straight into the next one looks like: the
    band never stops, but the sound before and after is different.
    """
    import numpy as np

    n = len(shares)
    w = window_seconds
    if n < 2 * w + 1:
        return []
    cumulative = np.cumsum(np.vstack([np.zeros((1, shares.shape[1])), shares]), axis=0)
    index = np.arange(w, n - w)
    before = (cumulative[index] - cumulative[index - w]) / w
    after = (cumulative[index + w] - cumulative[index]) / w
    change = np.zeros(n)
    change[index] = np.abs(before - after).sum(axis=1)

    out = []
    for t in range(w, n - w):
        lo, hi = max(0, t - spacing_seconds), min(n, t + spacing_seconds + 1)
        if change[t] >= min_change and change[t] == change[lo:hi].max():
            out.append(Break(
                start=float(t), end=float(t), depth_db=0.0, quiet_seconds=0.0,
                cut=float(t), score=0.4 * min(1.0, change[t] / 1.0), kind="change",
            ))
    return out


# ---------------------------------------------------------------------------
# Transcript anchors
# ---------------------------------------------------------------------------

@dataclass
class Anchor:
    """Evidence that song ``song_index`` (0-based) is playing at ``time``."""

    song_index: int
    time: float
    weight: float
    text: str = ""


_STOPWORDS = {
    "a", "an", "the", "of", "to", "in", "on", "and", "my", "me", "i", "you",
    "from", "for", "it", "is", "at", "hey", "oh", "yeah", "baby",
}
_WORD_RE = re.compile(r"[a-z0-9]+")
_EQUIVALENT = {"chile": "child", "coming": "comin", "comin": "comin", "foxey": "foxy"}


def _tokens(text: str) -> list[str]:
    text = re.sub(r"\([^)]*\)", " ", text.lower()).replace("'", "")
    return [_EQUIVALENT.get(tok, tok) for tok in _WORD_RE.findall(text)]


def transcript_words(transcript: dict) -> list[tuple[float, str]]:
    """Flatten a Whisper JSON transcript into (time, token) pairs.

    Uses word timestamps when present, otherwise spreads each segment's words
    evenly across the segment.
    """
    words: list[tuple[float, str]] = []
    for segment in transcript.get("segments", []):
        seg_words = segment.get("words") or []
        if seg_words:
            for word in seg_words:
                for tok in _tokens(str(word.get("word", ""))):
                    words.append((float(word.get("start", segment.get("start", 0.0))), tok))
            continue
        toks = _tokens(str(segment.get("text", "")))
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start))
        for i, tok in enumerate(toks):
            words.append((start + (end - start) * i / max(1, len(toks)), tok))
    words.sort(key=lambda item: item[0])
    return words


def find_anchors(titles: list[str], transcript: dict, max_word_gap_seconds: float = 4.0) -> list[Anchor]:
    """Find places in the transcript where a setlist title is sung or said.

    A full title in order ("room full of mirrors") is the strongest evidence.
    A single word counts only if it is distinctive: not a common word and not
    shared with another title in the setlist.
    """
    words = transcript_words(transcript)
    title_tokens = [_tokens(title) for title in titles]

    token_owner_count: dict[str, int] = {}
    for toks in title_tokens:
        for tok in set(toks):
            token_owner_count[tok] = token_owner_count.get(tok, 0) + 1

    anchors: list[Anchor] = []
    for song_index, toks in enumerate(title_tokens):
        if not toks:
            continue
        distinctive = {
            tok for tok in toks
            if tok not in _STOPWORDS and len(tok) > 3 and token_owner_count[tok] == 1
        }
        n = len(toks)
        i = 0
        while i < len(words):
            # Longest in-order run of the title starting at word i.
            matched = 0
            if words[i][1] == toks[0]:
                matched = 1
                last_time = words[i][0]
                while (
                    matched < n
                    and i + matched < len(words)
                    and words[i + matched][1] == toks[matched]
                    and words[i + matched][0] - last_time <= max_word_gap_seconds
                ):
                    last_time = words[i + matched][0]
                    matched += 1
            if matched == n and n >= 2:
                anchors.append(Anchor(song_index, words[i][0], 1.0, " ".join(toks)))
                i += matched
                continue
            if words[i][1] in distinctive:
                anchors.append(Anchor(song_index, words[i][0], 0.4, words[i][1]))
            i += 1
    anchors.sort(key=lambda a: a.time)
    return anchors


def load_transcript(transcript_file: Path) -> dict:
    data = json.loads(Path(transcript_file).read_text(encoding="utf-8"))
    if isinstance(data, list):  # a bare list of segments
        data = {"segments": data}
    return data


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

@dataclass
class SetlistSplit:
    """The result: a start and an end for every setlist entry.

    ``titles`` includes skip entries; ``segments()`` leaves them out.
    ``checks[i]`` lists reasons to listen to entry i's boundaries by ear.
    """

    titles: list[str]
    starts: list[float]
    ends: list[float] = field(default_factory=list)
    checks: list[list[str]] = field(default_factory=list)
    candidates: list[Break] = field(default_factory=list)
    anchors: list[Anchor] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    end: float | None = None       # end of the last entry (kept for callers that only need this)

    def __post_init__(self):
        if not self.ends:
            last = self.end if self.end is not None else (self.starts[-1] if self.starts else 0.0)
            self.ends = list(self.starts[1:]) + [last]
        if self.end is None:
            self.end = self.ends[-1]
        if not self.checks:
            self.checks = [[] for _ in self.titles]

    def cues(self) -> list[tuple[float, str]]:
        return [(start, title) for start, title in zip(self.starts, self.titles) if not is_skip_entry(title)]

    def segments(self) -> list[tuple[float, float, str]]:
        """(start, end, title) for every real song, in order."""
        return [
            (start, end, title)
            for start, end, title in zip(self.starts, self.ends, self.titles)
            if not is_skip_entry(title)
        ]


class _Sameness:
    """How unlike itself a stretch of music is (sum of squared deviations of
    the per-second chroma from the stretch's own average). A stretch that is
    all one song scores low; a stretch that spans two songs scores high.

    Seconds flagged in ``quiet`` are left out, so applause, talk and tuning
    between songs do not count against whichever song they end up in.
    """

    def __init__(self, chroma, quiet=None):
        import numpy as np

        chroma = np.asarray(chroma, dtype=np.float64)
        keep = np.ones(len(chroma)) if quiet is None else 1.0 - np.asarray(quiet, dtype=np.float64)[: len(chroma)]
        if len(keep) < len(chroma):
            keep = np.concatenate([keep, np.ones(len(chroma) - len(keep))])
        self._n = len(chroma)
        weighted = chroma * keep[:, None]
        self._sum = np.vstack([np.zeros((1, chroma.shape[1])), np.cumsum(weighted, axis=0)])
        self._sq = np.concatenate(([0.0], np.cumsum((weighted ** 2).sum(axis=1))))
        self._count = np.concatenate(([0.0], np.cumsum(keep)))

    def cost(self, start: float, end: float) -> float:
        a = max(0, min(self._n, int(round(start))))
        b = max(0, min(self._n, int(round(end))))
        count = self._count[b] - self._count[a]
        if count < 2:
            return 0.0
        total = self._sum[b] - self._sum[a]
        return float((self._sq[b] - self._sq[a]) - (total ** 2).sum() / count)


def quiet_seconds_mask(level_db, hop_seconds: float = LEVEL_HOP_SECONDS, drop_db: float = 10.0):
    """One flag per second: True where the level is in a dip."""
    import numpy as np

    level = np.asarray(level_db, dtype=np.float64)
    per_second = max(1, int(round(1.0 / hop_seconds)))
    seconds = len(level) // per_second
    if seconds == 0:
        return np.zeros(0, dtype=bool)
    mean = level[: seconds * per_second].reshape(seconds, per_second).mean(axis=1)
    return mean < (float(np.median(level)) - drop_db)


def announce_anchors(anchors: list[Anchor], candidates: list[Break]) -> list[Anchor]:
    """A title spoken during a break is an announcement of the next song.

    Move such anchors to just after that break's cut, so they count for the
    song that starts there and not for the one that has just ended.
    """
    moved = []
    for anchor in anchors:
        time = anchor.time
        for cand in candidates:
            if cand.kind == "break" and cand.start - 1.0 <= anchor.time <= cand.end + 1.0:
                time = max(time, cand.cut + 0.1)
                break
        moved.append(Anchor(anchor.song_index, time, anchor.weight, anchor.text))
    return moved


def choose_boundaries(
    candidates: list[Break],
    anchors: list[Anchor],
    song_count: int,
    first_start: float,
    end_time: float,
    chroma=None,
    quiet=None,
    min_song_seconds: float = 60.0,
    anchor_weight: float = 1.0,
    sameness_weight: float = 0.3,
    min_lengths: list[float] | None = None,
    return_candidates: bool = False,
):
    """Pick ``song_count - 1`` cuts, in order, from ``candidates``.

    Maximises
        sum of the chosen candidates' scores
      + anchor_weight   * weight of anchors that land inside their own song
      - sameness_weight * how unlike itself each resulting song is

    Returns the chosen cut times (or the chosen candidates themselves with
    ``return_candidates``), or None if there are not enough candidates to give
    every entry its minimum length: ``min_lengths[i]`` if given, otherwise
    ``min_song_seconds``.
    """
    needed = song_count - 1
    if needed <= 0:
        return []
    shortest = list(min_lengths) if min_lengths else [min_song_seconds] * song_count
    cands = sorted(
        (c for c in candidates if first_start + shortest[0] <= c.cut <= end_time - shortest[-1]),
        key=lambda c: c.cut,
    )
    if len(cands) < needed:
        return None

    per_song: list[list[Anchor]] = [[] for _ in range(song_count)]
    for anchor in anchors:
        if 0 <= anchor.song_index < song_count:
            per_song[anchor.song_index].append(anchor)
    sameness = _Sameness(chroma, quiet) if chroma is not None and len(chroma) else None

    def song_value(song: int, lo: float, hi: float) -> float:
        value = anchor_weight * sum(a.weight for a in per_song[song] if lo <= a.time < hi)
        if sameness is not None:
            value -= sameness_weight * sameness.cost(lo, hi)
        return value

    NEG = float("-inf")
    count = len(cands)
    best = [[NEG] * count for _ in range(needed)]
    back = [[-1] * count for _ in range(needed)]

    for c in range(count):
        best[0][c] = cands[c].score + song_value(0, first_start, cands[c].cut)

    for j in range(1, needed):
        for c in range(j, count):
            for prev in range(j - 1, c):
                if best[j - 1][prev] == NEG:
                    continue
                if cands[c].cut - cands[prev].cut < shortest[j]:
                    continue
                value = best[j - 1][prev] + cands[c].score + song_value(j, cands[prev].cut, cands[c].cut)
                if value > best[j][c]:
                    best[j][c] = value
                    back[j][c] = prev

    final_best, final_c = NEG, -1
    for c in range(count):
        if best[needed - 1][c] == NEG:
            continue
        value = best[needed - 1][c] + song_value(song_count - 1, cands[c].cut, end_time)
        if value > final_best:
            final_best, final_c = value, c
    if final_c < 0:
        return None

    chosen = []
    c = final_c
    for j in range(needed - 1, -1, -1):
        chosen.append(cands[c])
        c = back[j][c]
    chosen.reverse()
    return chosen if return_candidates else [cand.cut for cand in chosen]


def show_limits(level_db, duration: float, hop_seconds: float = LEVEL_HOP_SECONDS,
                drop_db: float = 10.0, edge_seconds: float = 120.0) -> tuple[float, float]:
    """Where the first song starts and the last song ends.

    Start: if the recording opens quiet (pre-show wait, an announcement), the
    first song starts when that opening quiet ends.
    End: the last song ends where the longest quiet stretch in the closing
    ``edge_seconds`` begins (the applause after the final note).
    """
    import numpy as np

    level = np.asarray(level_db, dtype=np.float64)
    if len(level) == 0:
        return 0.0, duration
    smoothed = _smooth(level, max(1, int(round(0.5 / hop_seconds))))
    reference = float(np.median(smoothed))
    dips = _dips(smoothed, reference, drop_db, hop_seconds, 0.5)

    first_start = 0.0
    opening = [dip for dip in _cluster(dips, 3.0)[:1] if dip[0][0] <= 5.0]
    if opening and opening[0][-1][1] < edge_seconds:
        first_start = opening[0][-1][1]

    end_time = duration
    closing = [dip for dip in dips if dip[0] >= duration - edge_seconds]
    if closing:
        longest = max(closing, key=lambda dip: dip[1] - dip[0])
        if longest[1] - longest[0] >= 3.0:
            end_time = longest[0]
    return first_start, end_time


def detect_setlist_boundaries(
    audio_file: Path,
    titles: list[str],
    transcript: dict | None = None,
    min_song_seconds: float = 60.0,
) -> SetlistSplit:
    """Find the start of every song in ``titles`` inside ``audio_file``."""
    if len(titles) < 1:
        raise RuntimeError("Setlist mode needs at least one song title.")

    samples = load_mono_audio(audio_file)
    duration = len(samples) / ANALYSIS_SAMPLE_RATE
    level = level_curve(samples)
    chroma, shares = tone_features(samples)
    beat = beat_strength(samples)
    return split_from_features(titles, level, chroma, shares, duration, transcript, min_song_seconds, beat=beat)


SKIP_MIN_SECONDS = 20.0


def split_from_features(titles, level, chroma, shares, duration: float,
                        transcript: dict | None = None,
                        min_song_seconds: float = 60.0,
                        beat=None) -> SetlistSplit:
    """The decision step, separated from audio decoding so it can be tested."""
    breaks = find_breaks(level)
    unpaused = find_changes(shares) + (find_beat_starts(beat) if beat is not None else [])
    changes = [
        c for c in unpaused
        if not any(b.kind == "break" and b.start - 3.0 <= c.cut <= b.end + 3.0 for b in breaks)
    ]
    candidates = sorted(breaks + changes, key=lambda c: c.cut)
    anchors = announce_anchors(find_anchors(titles, transcript), candidates) if transcript else []

    first_start, end_time = show_limits(level, duration)
    min_lengths = [SKIP_MIN_SECONDS if is_skip_entry(t) else min_song_seconds for t in titles]
    chosen = choose_boundaries(
        candidates, anchors, len(titles), first_start, end_time,
        chroma=chroma, quiet=quiet_seconds_mask(level),
        min_lengths=min_lengths, return_candidates=True,
    )
    if chosen is None:
        raise RuntimeError(
            f"Setlist mode found only {len(candidates)} possible boundaries for "
            f"{len(titles)} setlist entries. It cannot place every boundary."
        )

    starts = [first_start] + [cand.cut for cand in chosen]
    ends = [cand.stop() for cand in chosen] + [end_time]
    checks: list[list[str]] = [[] for _ in titles]
    reason = {
        "lull": "level only sags here, no clear pause",
        "change": "no pause here, placed where the sound changes",
        "beat": "no pause here, placed where a steady beat sets in",
    }
    for i, cand in enumerate(chosen):
        if cand.kind in reason:
            checks[i].append(f"end: {reason[cand.kind]}")
            checks[i + 1].append(f"start: {reason[cand.kind]}")

    notes = []
    if not transcript:
        notes.append("No transcript given: song order is not checked against the words.")
    return SetlistSplit(
        titles=list(titles), starts=starts, ends=ends, checks=checks,
        candidates=candidates, anchors=anchors, notes=notes, end=end_time,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def format_time(seconds: float) -> str:
    """mm:ss.s (minutes keep counting past 59, matching boundaries.txt)."""
    seconds = max(0.0, seconds)
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def format_boundaries(split: SetlistSplit) -> str:
    """The boundaries list, in the same layout as a hand-marked boundaries.txt.

    Check column: "ok", or "CHECK" for a boundary worth listening to. Skip
    entries are listed with "-" in place of a number and get no file. This
    text can be edited and passed back with --boundaries to re-export.
    """
    lines = ["#   Start     End       Check  Song"]
    reasons = []
    number = 0
    for title, start, end, why in zip(split.titles, split.starts, split.ends, split.checks):
        if is_skip_entry(title):
            label = "-"
        else:
            number += 1
            label = str(number)
        flag = "CHECK" if why else "ok"
        lines.append(f"{label:<3} {format_time(start):<9} {format_time(end):<9} {flag:<6} {title}")
        for item in why:
            reasons.append(f"  {title}: {item}")
    if reasons:
        lines.append("")
        lines.append("Listen to these:")
        lines.extend(reasons)
    return "\n".join(lines)


_BOUNDARY_LINE_RE = re.compile(
    r"^\s*(\d+)\s+(\d+(?::\d+){1,2}(?:\.\d+)?)\s+(\d+(?::\d+){1,2}(?:\.\d+)?)\s+(.*\S)\s*$"
)
_FLAG_WORDS = {"ok", "check", "y", "n", "-", "_", "?"}


def _clock_to_seconds(text: str) -> float:
    seconds = 0.0
    for part in text.split(":"):
        seconds = seconds * 60.0 + float(part)
    return seconds


def read_boundaries_file(boundaries_file: Path) -> list[tuple[float, float, str]]:
    """Read (start, end, title) for each numbered song in a boundaries file.

    Works on the list setlist mode prints and on a hand-marked answer key:
    "<number> <start> <end> [one flag word] <title>". Lines without a number
    (headers, notes, skip entries marked "-") are ignored.
    """
    segments = []
    for line in Path(boundaries_file).read_text(encoding="utf-8").splitlines():
        match = _BOUNDARY_LINE_RE.match(line)
        if not match:
            continue
        start = _clock_to_seconds(match.group(2))
        end = _clock_to_seconds(match.group(3))
        rest = match.group(4).split(None, 1)
        if len(rest) == 2 and rest[0].lower() in _FLAG_WORDS:
            title = rest[1].strip()
        else:
            title = match.group(4).strip()
        if end > start:
            segments.append((start, end, title))
    return segments
