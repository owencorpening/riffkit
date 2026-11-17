#!/usr/bin/env python3
"""
Time one song through riffkit's whole chain and check the result.

    .venv/bin/python scripts/benchmark.py "<song file>"

Runs the same steps as the main command (stems, lyrics, REAPER project),
times each one, records the peak memory, checks that the output is sane,
and appends one line to a log (data/benchmarks.csv by default) so runs can
be compared over time and across riffkit versions.

This is a measurement you run on purpose, not part of the normal tests: it
needs a real song, takes minutes and several GB of memory. Timings vary with
whatever else the machine is doing, so compare trends, not single runs.

Linux only for the memory figures (they come from /proc); elsewhere they are
left blank and everything else still works.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import reaper_project  # noqa: E402
import riftkit  # noqa: E402

LOG_FIELDS = [
    "date", "commit", "cpu", "total_mem_mb", "available_mem_mb_at_start",
    "song", "song_seconds", "stem_model", "lyrics_model",
    "stems_seconds", "lyrics_seconds", "project_seconds", "total_seconds",
    "stems_peak_mb", "lyrics_peak_mb", "lowest_available_mb",
    "checks", "problems",
]


# ---------------------------------------------------------------------------
# Machine facts and memory sampling (Linux /proc)
# ---------------------------------------------------------------------------

def _meminfo_mb(key: str, path: Path = Path("/proc/meminfo")) -> int | None:
    try:
        for line in path.read_text().splitlines():
            if line.startswith(key + ":"):
                return int(line.split()[1]) // 1024
    except OSError:
        pass
    return None


def cpu_name(path: Path = Path("/proc/cpuinfo")) -> str:
    try:
        for line in path.read_text().splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""


def process_tree_rss_mb(root_pid: int, proc: Path = Path("/proc")) -> int | None:
    """Resident memory of a process and all its descendants, in MB."""
    if not (proc / str(root_pid)).exists():
        return None
    total_kb = 0
    stack = [root_pid]
    seen = set()
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        base = proc / str(pid)
        try:
            for line in (base / "status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    total_kb += int(line.split()[1])
                    break
        except OSError:
            continue
        try:
            for task in (base / "task").iterdir():
                children = (task / "children").read_text().split()
                stack.extend(int(child) for child in children)
        except OSError:
            pass
    return total_kb // 1024


class MemorySampler:
    """Samples this process tree's memory and the system's free memory."""

    def __init__(self, interval: float = 0.5):
        self.interval = interval
        self.peak_mb: int | None = None
        self.lowest_available_mb: int | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            rss = process_tree_rss_mb(os.getpid())
            avail = _meminfo_mb("MemAvailable")
            if rss is not None:
                self.peak_mb = rss if self.peak_mb is None else max(self.peak_mb, rss)
            if avail is not None:
                self.lowest_available_mb = (
                    avail if self.lowest_available_mb is None else min(self.lowest_available_mb, avail)
                )
            self._stop.wait(self.interval)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()


# ---------------------------------------------------------------------------
# Output checks
# ---------------------------------------------------------------------------

def wav_has_sound(path: Path, threshold: float = 1e-4) -> bool:
    """True if a 16-bit or 32-bit PCM WAV has any sample above ``threshold``."""
    import numpy as np

    try:
        with wave.open(str(path), "rb") as handle:
            width = handle.getsampwidth()
            frames = handle.readframes(handle.getnframes())
    except (wave.Error, OSError, EOFError):
        return _ffmpeg_has_sound(path)
    if width == 2:
        data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 4:
        data = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        return _ffmpeg_has_sound(path)
    return bool(data.size) and float(np.abs(data).max()) > threshold


def _ffmpeg_has_sound(path: Path) -> bool:
    result = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    for line in result.stderr.splitlines():
        if "max_volume:" in line:
            try:
                return float(line.split("max_volume:")[1].split()[0]) > -80.0
            except ValueError:
                return False
    return False


def check_output(stems_dir: Path, project_file: Path, lyrics_expected: bool) -> list[str]:
    """Problems with a finished run; an empty list means it looks right."""
    problems = []
    stems = reaper_project.match_stem_files(stems_dir)
    for track, _ in reaper_project.STEM_TRACKS:
        path = stems.get(track)
        if path is None:
            problems.append(f"no {track} stem")
        elif not wav_has_sound(path):
            problems.append(f"{track} stem is silent")
    if not project_file.exists():
        problems.append("no project file")
        return problems
    text = project_file.read_text(encoding="utf-8", errors="replace")
    tracks = text.count("<TRACK")
    expected = len(reaper_project.STEM_TRACKS) + 1 + (1 if lyrics_expected else 0)
    if tracks != expected:
        problems.append(f"project has {tracks} tracks, expected {expected}")
    if 'NAME "Original"' not in text:
        problems.append("project has no Original track")
    if lyrics_expected and 'NAME "Lyrics"' not in text:
        problems.append("project has no Lyrics track")
    return problems


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------

def append_log(log_file: Path, row: dict) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    new = not log_file.exists() or log_file.stat().st_size == 0
    with log_file.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_FIELDS)
        if new:
            writer.writeheader()
        writer.writerow({key: row.get(key, "") for key in LOG_FIELDS})


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def _timed(label: str, func):
    print(f"\n=== {label} ===", flush=True)
    with MemorySampler() as sampler:
        start = time.monotonic()
        result = func()
        seconds = time.monotonic() - start
    return result, seconds, sampler


def benchmark(song: Path, output_dir: Path, stem_model: str, lyrics_model: str,
              lyrics: bool = True) -> dict:
    row: dict = {
        "date": dt.datetime.now().isoformat(timespec="seconds"),
        "commit": git_commit(),
        "cpu": cpu_name(),
        "total_mem_mb": _meminfo_mb("MemTotal"),
        "available_mem_mb_at_start": _meminfo_mb("MemAvailable"),
        "song": song.name,
        "song_seconds": round(reaper_project.media_duration(song), 1),
        "stem_model": stem_model,
        "lyrics_model": lyrics_model if lyrics else "",
    }
    lowest = []
    total_start = time.monotonic()

    stems_dir, row["stems_seconds"], sampler = _timed(
        "stems", lambda: riftkit.separate_stems(song, output_dir, model=stem_model))
    row["stems_peak_mb"] = sampler.peak_mb
    lowest.append(sampler.lowest_available_mb)

    project_file = stems_dir / f"{song.stem}.RPP"
    segments = None
    if lyrics:
        vocals = reaper_project.match_stem_files(stems_dir).get("Vocals")
        transcript = stems_dir / "lyrics.json"
        ok, row["lyrics_seconds"], sampler = _timed(
            "lyrics",
            lambda: vocals is not None and riftkit.transcribe_vocals(vocals, transcript, model=lyrics_model),
        )
        row["lyrics_peak_mb"] = sampler.peak_mb
        lowest.append(sampler.lowest_available_mb)
        if ok:
            segments = reaper_project.load_lyrics(transcript)

    _, row["project_seconds"], sampler = _timed(
        "project",
        lambda: reaper_project.write_reaper_project(project_file, stems_dir, original=song, lyrics=segments),
    )
    lowest.append(sampler.lowest_available_mb)

    row["total_seconds"] = time.monotonic() - total_start
    for key in ("stems_seconds", "lyrics_seconds", "project_seconds", "total_seconds"):
        if key in row:
            row[key] = round(row[key], 1)
    known = [value for value in lowest if value is not None]
    row["lowest_available_mb"] = min(known) if known else ""

    problems = check_output(stems_dir, project_file, lyrics_expected=lyrics)
    if lyrics and not segments:
        problems.append("no lyrics transcribed")
    row["checks"] = "ok" if not problems else "FAILED"
    row["problems"] = "; ".join(problems)
    row["_project"] = str(project_file)
    return row


def _minutes(seconds) -> str:
    if seconds in ("", None):
        return "-"
    return f"{int(seconds // 60)}m {int(seconds % 60):02d}s"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("song", help="A song file (WAV, MP3, FLAC, M4A, Opus)")
    parser.add_argument("--output", help="Where to write the run (default: a temporary folder, deleted after)")
    parser.add_argument("--stem-model", default=riftkit.DEMUCS_MODEL)
    parser.add_argument("--lyrics-model", default=riftkit.LYRICS_MODEL)
    parser.add_argument("--no-lyrics", action="store_true", help="Time stems and project only")
    parser.add_argument("--log", default=str(REPO / "data" / "benchmarks.csv"),
                        help="CSV log to append to (default: data/benchmarks.csv)")
    args = parser.parse_args(argv)

    song = Path(args.song).expanduser().resolve()
    if not song.exists():
        print(f"Song not found: {song}", file=sys.stderr)
        return 2

    keep = args.output is not None
    output_dir = Path(args.output).expanduser().resolve() if keep else Path(tempfile.mkdtemp(prefix="riffkit-bench-"))
    try:
        row = benchmark(song, output_dir, args.stem_model, args.lyrics_model, lyrics=not args.no_lyrics)
    finally:
        if not keep:
            shutil.rmtree(output_dir, ignore_errors=True)

    project = row.pop("_project")
    append_log(Path(args.log).expanduser(), row)

    print(f"""
=== Benchmark: {row['song']} ({_minutes(row['song_seconds'])} long) ===
  Machine:  {row['cpu'] or 'unknown CPU'}, {row['total_mem_mb'] or '?'} MB memory,
            {row['available_mem_mb_at_start'] or '?'} MB available at start
  Stems:    {_minutes(row['stems_seconds'])}  (peak {row.get('stems_peak_mb') or '?'} MB, {row['stem_model']})
  Lyrics:   {_minutes(row.get('lyrics_seconds'))}  (peak {row.get('lyrics_peak_mb') or '?'} MB, {row['lyrics_model'] or 'skipped'})
  Project:  {_minutes(row['project_seconds'])}
  Total:    {_minutes(row['total_seconds'])}
  Lowest free memory during the run: {row['lowest_available_mb'] or '?'} MB
  Checks:   {row['checks']}{(' - ' + row['problems']) if row['problems'] else ''}
  Logged to {args.log}""")
    if keep:
        print(f"  Project:  {project}")
    return 0 if row["checks"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
