#!/usr/bin/env python3
"""
riftkit: MP3 to practice-ready REAPER project

Usage:
    ./riftkit.py <song.mp3>
    ./riftkit.py <song.mp3> --output ~/music/projects
    ./riftkit.py <song.mp3> --no-lyrics
    ./riftkit.py <concert.mp3> --split-concert

Steps:
    1. Separate stems with Demucs (vocals, drums, bass, other)
    2. Transcribe vocals with Whisper          [TODO]
    3. Copy REAPER template with stems folder  [TODO]
    4. Insert lyrics into REAPER project       [TODO]

Requires:
    pip install demucs

Author: Owen Corpening
License: MIT
"""

import sys
import argparse
import subprocess
import shutil
import json
import re
from pathlib import Path


TEMPLATE_RPP = Path(__file__).parent / "stem-separation" / "stem_template.RPP"
DEMUCS_MODEL = "htdemucs"  # 4-stem model: vocals, drums, bass, other

SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")
SILENCE_END_RE = re.compile(
    r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)"
)
TIMESTAMP_LINE_RE = re.compile(
    r"""^\s*\[?
    (?P<timestamp>(?:\d+:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?)
    \]?
    (?:\s*[-–—:|]\s*|\s+)?
    (?P<title>.*\S)?
    \s*$""",
    re.VERBOSE,
)


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"{name} is required but was not found on PATH")


def sanitize_filename(name: str) -> str:
    """Return a filesystem-safe filename fragment."""
    cleaned = re.sub(r"[\\/:*?\"<>|]", "_", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "untitled"


def parse_song_titles(song_list_file: Path) -> list[str]:
    """Parse a sidecar text file that contains one song title per line."""
    lines = song_list_file.read_text(encoding="utf-8").splitlines()
    titles: list[str] = []
    has_explicit_songs_section = any(line.strip().lower() == "songs:" for line in lines)
    in_songs_section = False
    in_leading_title_block = not has_explicit_songs_section

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if not titles:
                continue
            in_leading_title_block = False
            continue
        if line.lower() == "songs:":
            in_songs_section = True
            in_leading_title_block = False
            continue
        if line.lower().startswith(("date:", "venue:", "setlist:", "concert:")):
            in_leading_title_block = False
            continue
        if has_explicit_songs_section and not in_songs_section:
            continue
        if not has_explicit_songs_section and not in_leading_title_block:
            continue
        line = re.sub(r"^\d+[\).\-\:]?\s*", "", line)
        if line:
            titles.append(line)

    return titles


def parse_timestamp(timestamp_text: str) -> float:
    """Convert a timestamp like mm:ss, hh:mm:ss, or mm:ss.mmm to seconds."""
    normalized = timestamp_text.strip().replace(",", ".")
    parts = normalized.split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"Unsupported timestamp format: {timestamp_text!r}")

    seconds = float(parts[-1])
    minutes = int(parts[-2])
    hours = int(parts[-3]) if len(parts) == 3 else 0
    return hours * 3600 + minutes * 60 + seconds


def parse_song_cues(song_list_file: Path) -> list[tuple[float, str]]:
    """Parse a sidecar text file that contains timestamped song starts."""
    lines = song_list_file.read_text(encoding="utf-8").splitlines()
    cues: list[tuple[float, str]] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.lower() == "songs:":
            continue

        match = TIMESTAMP_LINE_RE.match(line)
        if not match:
            continue

        timestamp = parse_timestamp(match.group("timestamp"))
        title = (match.group("title") or "").strip()
        title = re.sub(r"^[\s\-–—:|]+", "", title)
        title = re.sub(r"^[\[(]+", "", title)
        if not title:
            title = f"song_{len(cues) + 1:02d}"
        cues.append((timestamp, title))

    return cues


def separate_stems(audio_file: Path, output_dir: Path) -> Path:
    """Run Demucs on audio_file; return the folder containing the stem WAVs."""
    print(f"Separating stems: {audio_file.name}")

    result = subprocess.run(
        [sys.executable, "-m", "demucs", "--out", str(output_dir), str(audio_file)],
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Demucs failed — is it installed? pip install demucs")

    stems_dir = output_dir / DEMUCS_MODEL / audio_file.stem
    if not stems_dir.exists():
        raise FileNotFoundError(
            f"Expected stems at {stems_dir} but it was not created."
        )

    stem_files = list(stems_dir.glob("*.wav"))
    print(f"  Stems → {stems_dir}")
    for f in sorted(stem_files):
        print(f"    {f.name}")

    return stems_dir


def copy_template(stems_dir: Path) -> Path:
    """Copy stem_template.RPP next to the stems folder and return the path."""
    if not TEMPLATE_RPP.exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_RPP}")

    dest = stems_dir.parent / "stem_template.RPP"
    shutil.copy(TEMPLATE_RPP, dest)
    print(f"  Template → {dest}")
    return dest


def probe_duration(audio_file: Path) -> float:
    """Return the duration of audio_file in seconds using ffprobe."""
    require_tool("ffprobe")
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_file),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {audio_file.name}: {result.stderr.strip()}")
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"Could not read duration for {audio_file.name}") from exc


def detect_silence_intervals(
    audio_file: Path,
    silence_threshold_db: float,
    min_silence_seconds: float,
) -> list[tuple[float, float]]:
    """Return (start, end) pairs for detected silences."""
    require_tool("ffmpeg")
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(audio_file),
            "-af",
            f"silencedetect=noise={silence_threshold_db}dB:d={min_silence_seconds}",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    stderr = result.stderr or ""
    silences: list[tuple[float, float]] = []
    current_start = None
    for line in stderr.splitlines():
        start_match = SILENCE_START_RE.search(line)
        if start_match:
            current_start = float(start_match.group(1))
            continue

        end_match = SILENCE_END_RE.search(line)
        if end_match:
            end = float(end_match.group(1))
            if current_start is None:
                duration = float(end_match.group(2))
                current_start = end - duration
            silences.append((current_start, end))
            current_start = None

    return silences


def build_song_segments(
    duration: float,
    silence_intervals: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Convert silence intervals into song segments."""
    segments: list[tuple[float, float]] = []
    cursor = 0.0

    for silence_start, silence_end in silence_intervals:
        if silence_start > cursor:
            segments.append((cursor, silence_start))
        cursor = max(cursor, silence_end)

    if duration > cursor:
        segments.append((cursor, duration))

    return [(start, end) for start, end in segments if end - start > 1.0]


def build_song_segments_from_cues(
    duration: float,
    song_cues: list[tuple[float, str]],
) -> list[tuple[float, float, str]]:
    """Convert timestamped song cues into (start, end, title) segments."""
    seen_starts: set[float] = set()
    cues: list[tuple[float, str]] = []
    for start, title in sorted(song_cues, key=lambda item: item[0]):
        if start < 0 or start > duration:
            continue
        if start in seen_starts:
            continue
        seen_starts.add(start)
        cues.append((start, title))

    segments: list[tuple[float, float, str]] = []
    for i, (start, title) in enumerate(cues):
        end = cues[i + 1][0] if i + 1 < len(cues) else duration
        if end - start > 1.0:
            segments.append((start, end, title))

    return segments


def export_segment(
    audio_file: Path,
    dest_file: Path,
    start: float,
    end: float,
) -> None:
    """Export one segment using ffmpeg."""
    require_tool("ffmpeg")
    codec_args = []
    suffix = dest_file.suffix.lower()
    if suffix == ".mp3":
        codec_args = ["-c:a", "libmp3lame", "-q:a", "2"]
    elif suffix == ".wav":
        codec_args = ["-c:a", "pcm_s16le"]

    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(audio_file),
            *codec_args,
            str(dest_file),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed while exporting {dest_file.name}: {result.stderr.strip()}")


def split_concert_into_songs(
    audio_file: Path,
    output_dir: Path,
    silence_threshold_db: float = -35.0,
    min_silence_seconds: float = 8.0,
    song_cues: list[tuple[float, str]] | None = None,
    song_titles: list[str] | None = None,
) -> Path:
    """Split a concert file into numbered song files using silence gaps."""
    duration = probe_duration(audio_file)
    cue_segments = build_song_segments_from_cues(duration, song_cues or [])
    if cue_segments:
        segments = cue_segments
        use_cues = True
    else:
        silences = detect_silence_intervals(audio_file, silence_threshold_db, min_silence_seconds)
        segments = build_song_segments(duration, silences)
        use_cues = False

    if use_cues:
        if len(segments) < 1:
            raise RuntimeError(
                "Could not find any valid timestamp cues in the sidecar text file."
            )
    elif len(segments) < 2:
        raise RuntimeError(
            "Could not find enough silence gaps to split the concert into songs. "
            "Try lowering the silence threshold or using a longer minimum silence."
        )

    split_dir = output_dir / f"{audio_file.stem}_songs"
    split_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    output_suffix = audio_file.suffix.lower() if audio_file.suffix.lower() in {".mp3", ".wav"} else ".wav"
    titles = song_titles or []

    print(f"Splitting concert: {audio_file.name}")
    print(f"  Output → {split_dir}")
    for i, segment in enumerate(segments, start=1):
        if use_cues:
            start, end, title = segment
        else:
            start, end = segment
            title = titles[i - 1] if i - 1 < len(titles) else f"song_{i:02d}"
        file_stem = f"{i:02d} - {sanitize_filename(title)}"
        song_name = f"{file_stem}{output_suffix}"
        dest_file = split_dir / song_name
        export_segment(audio_file, dest_file, start, end)
        manifest.append(
            {
                "index": i,
                "file": song_name,
                "title": title,
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
            }
        )
        print(f"  {song_name}  [{start:.1f}s → {end:.1f}s]")

    (split_dir / "segments.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return split_dir


def main():
    parser = argparse.ArgumentParser(
        description="Process an audio file into a practice-ready REAPER project"
    )
    parser.add_argument("audio_file", help="Input audio file (MP3, WAV, FLAC, …)")
    parser.add_argument(
        "--output", help="Output directory (default: ./projects)", default="./projects"
    )
    parser.add_argument(
        "--no-lyrics", action="store_true", help="Skip lyrics transcription"
    )
    parser.add_argument(
        "--split-concert",
        action="store_true",
        help="Split a long concert recording into separate song files before processing",
    )
    parser.add_argument(
        "--silence-threshold-db",
        type=float,
        default=-35.0,
        help="Silence threshold in dB for concert splitting (default: -35.0)",
    )
    parser.add_argument(
        "--min-silence-seconds",
        type=float,
        default=8.0,
        help="Minimum silence length in seconds for concert splitting (default: 8.0)",
    )
    parser.add_argument(
        "--song-list",
        help="Sidecar text file with one song title per line, in order",
    )

    args = parser.parse_args()

    audio_file = Path(args.audio_file).expanduser().resolve()
    if not audio_file.exists():
        print(f"Error: file not found: {audio_file}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nProcessing: {audio_file.name}")
    print(f"Output:     {output_dir}\n")

    if args.split_concert:
        song_list_file = Path(args.song_list).expanduser().resolve() if args.song_list else audio_file.with_suffix(".txt")
        song_cues = parse_song_cues(song_list_file) if song_list_file.exists() else []
        song_titles = parse_song_titles(song_list_file) if song_list_file.exists() and not song_cues else []
        if song_cues:
            print(f"Using timestamp cues from: {song_list_file}")
        elif song_titles:
            print(f"Using song titles from: {song_list_file}")
        split_concert_into_songs(
            audio_file,
            output_dir,
            silence_threshold_db=args.silence_threshold_db,
            min_silence_seconds=args.min_silence_seconds,
            song_cues=song_cues,
            song_titles=song_titles,
        )
        return

    # Step 1: Stem separation
    stems_dir = separate_stems(audio_file, output_dir)

    # Step 2: Copy REAPER template alongside stems
    rpp_path = copy_template(stems_dir)

    # Step 3: Lyrics transcription (TODO)
    if not args.no_lyrics:
        print("\n[TODO] Lyrics transcription not yet implemented.")
        print("       Run lyrics-sync/transcribe.py manually for now.")

    print(f"""
Done!
  Stems:    {stems_dir}
  Template: {rpp_path}

Next steps:
  1. Open {rpp_path.name} in REAPER
  2. Run Actions > import_stems.lua and select any file in the stems folder
""")


if __name__ == "__main__":
    main()
