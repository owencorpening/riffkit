import csv
import importlib.util
import os
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

np = pytest.importorskip("numpy")

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("benchmark", ROOT / "scripts" / "benchmark.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def _wav(path: Path, amplitude: float, seconds: float = 0.5, rate: int = 8000):
    samples = (np.sin(np.arange(int(seconds * rate)) / 5.0) * amplitude * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.tobytes())
    return path


def _stems(folder: Path, silent=()):
    folder.mkdir(parents=True)
    for name in ("vocals", "drums", "bass", "other"):
        _wav(folder / f"{name}.wav", 0.0 if name in silent else 0.5)
    return folder


def test_wav_has_sound_tells_sound_from_silence(tmp_path):
    assert benchmark.wav_has_sound(_wav(tmp_path / "loud.wav", 0.5))
    assert not benchmark.wav_has_sound(_wav(tmp_path / "quiet.wav", 0.0))


def test_check_output_passes_a_complete_run(tmp_path):
    stems = _stems(tmp_path / "song")
    original = _wav(tmp_path / "song.wav", 0.5)
    project = benchmark.reaper_project.write_reaper_project(
        stems / "song.RPP", stems, original=original, length_seconds=0.5,
        lyrics=[{"start": 0.0, "end": 0.4, "text": "hello"}],
    )
    assert benchmark.check_output(stems, project, lyrics_expected=True) == []


def test_check_output_reports_silent_stem_and_missing_lyrics(tmp_path):
    stems = _stems(tmp_path / "song", silent=("drums",))
    original = _wav(tmp_path / "song.wav", 0.5)
    project = benchmark.reaper_project.write_reaper_project(
        stems / "song.RPP", stems, original=original, length_seconds=0.5,
    )
    problems = benchmark.check_output(stems, project, lyrics_expected=True)
    assert "Drums stem is silent" in problems
    assert any("tracks, expected 6" in p for p in problems)
    assert "project has no Lyrics track" in problems


def test_check_output_without_project(tmp_path):
    stems = _stems(tmp_path / "song")
    assert benchmark.check_output(stems, stems / "missing.RPP", lyrics_expected=False) == ["no project file"]


def test_append_log_writes_header_once(tmp_path):
    log = tmp_path / "data" / "benchmarks.csv"
    benchmark.append_log(log, {"song": "a.wav", "total_seconds": 10.0, "ignored": "x"})
    benchmark.append_log(log, {"song": "b.wav", "total_seconds": 20.0})
    rows = list(csv.DictReader(log.open()))
    assert [r["song"] for r in rows] == ["a.wav", "b.wav"]
    assert list(rows[0].keys()) == benchmark.LOG_FIELDS


def test_meminfo_and_cpu_parsing(tmp_path):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       14336000 kB\nMemAvailable:    6144000 kB\n")
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("processor\t: 0\nmodel name\t: AMD Ryzen 7 5700U with Radeon Graphics\n")
    assert benchmark._meminfo_mb("MemTotal", meminfo) == 14000
    assert benchmark._meminfo_mb("MemAvailable", meminfo) == 6000
    assert benchmark._meminfo_mb("Missing", meminfo) is None
    assert benchmark.cpu_name(cpuinfo) == "AMD Ryzen 7 5700U with Radeon Graphics"
    assert benchmark.cpu_name(tmp_path / "absent") == ""


@pytest.mark.skipif(not Path("/proc/self/status").exists(), reason="needs Linux /proc")
def test_process_tree_rss_counts_this_process():
    assert benchmark.process_tree_rss_mb(os.getpid()) > 0
    assert benchmark.process_tree_rss_mb(10 ** 9) is None


def test_benchmark_runs_the_chain_and_logs(tmp_path):
    song = _wav(tmp_path / "Song.wav", 0.5)
    out = tmp_path / "out"

    def fake_separate(audio, output_dir, model):
        return _stems(output_dir / model / audio.stem)

    def fake_transcribe(vocals, output, model):
        output.write_text('{"segments": [{"start": 0.0, "end": 0.4, "text": "hi"}]}')
        return True

    log = tmp_path / "bench.csv"
    with patch.object(benchmark.riffkit, "separate_stems", side_effect=fake_separate), \
            patch.object(benchmark.riffkit, "transcribe_vocals", side_effect=fake_transcribe):
        code = benchmark.main([str(song), "--output", str(out), "--log", str(log)])

    assert code == 0
    row = list(csv.DictReader(log.open()))[0]
    assert row["song"] == "Song.wav"
    assert row["checks"] == "ok"
    assert row["stem_model"] == benchmark.riffkit.DEMUCS_MODEL
    assert float(row["total_seconds"]) >= 0
    assert (out / benchmark.riffkit.DEMUCS_MODEL / "Song" / "Song.RPP").exists()


def test_benchmark_reports_failure_and_cleans_temporary_output(tmp_path):
    song = _wav(tmp_path / "Song.wav", 0.5)
    made = []

    def fake_separate(audio, output_dir, model):
        made.append(output_dir)
        return _stems(output_dir / model / audio.stem, silent=("bass",))

    log = tmp_path / "bench.csv"
    with patch.object(benchmark.riffkit, "separate_stems", side_effect=fake_separate):
        code = benchmark.main([str(song), "--no-lyrics", "--log", str(log)])

    assert code == 1
    row = list(csv.DictReader(log.open()))[0]
    assert row["checks"] == "FAILED"
    assert "Bass stem is silent" in row["problems"]
    assert not made[0].exists()          # temporary run folder removed
