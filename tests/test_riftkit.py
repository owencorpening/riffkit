import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import riftkit


# ---------------------------------------------------------------------------
# separate_stems
# ---------------------------------------------------------------------------

def test_separate_stems_returns_correct_path(tmp_path):
    stems_dir = tmp_path / "htdemucs" / "mysong"
    stems_dir.mkdir(parents=True)
    (stems_dir / "vocals.wav").touch()

    audio = tmp_path / "mysong.mp3"
    audio.touch()

    with patch("riftkit.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = riftkit.separate_stems(audio, tmp_path)

    assert result == stems_dir


def test_separate_stems_raises_on_demucs_failure(tmp_path):
    audio = tmp_path / "song.mp3"
    audio.touch()

    with patch("riftkit.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        with pytest.raises(RuntimeError, match="Demucs failed"):
            riftkit.separate_stems(audio, tmp_path)


def test_separate_stems_raises_when_output_missing(tmp_path):
    audio = tmp_path / "song.mp3"
    audio.touch()

    with patch("riftkit.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        # htdemucs/song/ is never created
        with pytest.raises(FileNotFoundError):
            riftkit.separate_stems(audio, tmp_path)


def test_separate_stems_passes_correct_args(tmp_path):
    stems_dir = tmp_path / "htdemucs" / "song"
    stems_dir.mkdir(parents=True)

    audio = tmp_path / "song.flac"
    audio.touch()

    with patch("riftkit.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        riftkit.separate_stems(audio, tmp_path)

    call_args = mock_run.call_args[0][0]
    assert "-m" in call_args
    assert "demucs" in call_args
    assert "--out" in call_args
    assert str(tmp_path) in call_args
    assert str(audio) in call_args


# ---------------------------------------------------------------------------
# copy_template
# ---------------------------------------------------------------------------

def test_copy_template_copies_rpp(tmp_path):
    stems_dir = tmp_path / "htdemucs" / "song"
    stems_dir.mkdir(parents=True)

    fake_template = tmp_path / "stem_template.RPP"
    fake_template.write_text("<REAPER_PROJECT />")

    with patch.object(riftkit, "TEMPLATE_RPP", fake_template):
        dest = riftkit.copy_template(stems_dir)

    assert dest == tmp_path / "htdemucs" / "stem_template.RPP"
    assert dest.exists()
    assert dest.read_text() == "<REAPER_PROJECT />"


def test_copy_template_raises_when_template_missing(tmp_path):
    stems_dir = tmp_path / "stems"
    stems_dir.mkdir()

    missing = tmp_path / "nonexistent.RPP"

    with patch.object(riftkit, "TEMPLATE_RPP", missing):
        with pytest.raises(FileNotFoundError, match="Template not found"):
            riftkit.copy_template(stems_dir)


# ---------------------------------------------------------------------------
# main (integration-level argument handling)
# ---------------------------------------------------------------------------

def test_main_exits_on_missing_audio(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        with patch("sys.argv", ["riftkit.py", str(tmp_path / "ghost.mp3")]):
            riftkit.main()
    assert exc.value.code == 1


def test_main_runs_full_flow(tmp_path):
    audio = tmp_path / "song.mp3"
    audio.touch()

    stems_dir = tmp_path / "out" / "htdemucs" / "song"
    stems_dir.mkdir(parents=True)
    (stems_dir / "vocals.wav").touch()

    fake_template = tmp_path / "stem_template.RPP"
    fake_template.write_text("<REAPER_PROJECT />")

    with patch("sys.argv", ["riftkit.py", str(audio), "--output", str(tmp_path / "out"), "--no-lyrics"]), \
         patch("riftkit.subprocess.run", return_value=MagicMock(returncode=0)), \
         patch.object(riftkit, "TEMPLATE_RPP", fake_template):
        riftkit.main()

    assert (stems_dir.parent / "stem_template.RPP").exists()
