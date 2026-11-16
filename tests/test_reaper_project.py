import re
from pathlib import Path

import pytest

import reaper_project as rp


def _stems(tmp_path, names=("vocals", "drums", "bass", "other"), suffix=".wav"):
    stems_dir = tmp_path / "htdemucs_ft" / "song"
    stems_dir.mkdir(parents=True)
    for name in names:
        (stems_dir / f"{name}{suffix}").write_bytes(b"\0")
    return stems_dir


def test_match_stem_files_maps_demucs_names_to_tracks(tmp_path):
    stems_dir = _stems(tmp_path)
    found = rp.match_stem_files(stems_dir)
    assert {k: v.name for k, v in found.items()} == {
        "Vocals": "vocals.wav", "Drums": "drums.wav", "Bass": "bass.wav", "Other": "other.wav",
    }


def test_match_stem_files_ignores_non_audio_and_unknown(tmp_path):
    stems_dir = _stems(tmp_path, names=("vocals", "notes"))
    (stems_dir / "readme.txt").write_text("x")
    assert list(rp.match_stem_files(stems_dir)) == ["Vocals"]


def test_write_project_puts_each_stem_on_its_track(tmp_path):
    stems_dir = _stems(tmp_path)
    project = rp.write_reaper_project(stems_dir / "song.RPP", stems_dir, length_seconds=185.5)
    text = project.read_text()

    assert text.startswith("<REAPER_PROJECT")
    assert text.rstrip().endswith(">")
    names = re.findall(r'^\s*NAME "([^"]+)"$', text, re.M)
    assert names == ["Vocals", "vocals.wav", "Drums", "drums.wav", "Bass", "bass.wav", "Other", "other.wav"]
    assert text.count("<ITEM") == 4
    assert "LENGTH 185.500000" in text
    assert '<SOURCE WAVE\n        FILE "vocals.wav"' in text


def test_write_project_uses_paths_relative_to_the_project_file(tmp_path):
    stems_dir = _stems(tmp_path)
    original = tmp_path / "song.mp3"
    original.write_bytes(b"\0")
    project = rp.write_reaper_project(stems_dir / "song.RPP", stems_dir, original=original, length_seconds=10)
    text = project.read_text()
    assert 'FILE "../../song.mp3"' in text
    assert "<SOURCE MP3" in text


def test_original_track_is_muted_and_last(tmp_path):
    stems_dir = _stems(tmp_path)
    original = tmp_path / "song.mp3"
    original.write_bytes(b"\0")
    project = rp.write_reaper_project(stems_dir / "song.RPP", stems_dir, original=original, length_seconds=10)
    tracks = project.read_text().split("<TRACK")[1:]
    assert len(tracks) == 5
    assert 'NAME "Original"' in tracks[-1]
    assert "MUTESOLO 1 0 0" in tracks[-1]
    assert all("MUTESOLO 0 0 0" in t for t in tracks[:-1])


def test_missing_stem_leaves_an_empty_track(tmp_path):
    stems_dir = _stems(tmp_path, names=("vocals", "drums", "other"))
    project = rp.write_reaper_project(stems_dir / "song.RPP", stems_dir, length_seconds=10)
    tracks = project.read_text().split("<TRACK")[1:]
    bass = [t for t in tracks if 'NAME "Bass"' in t][0]
    assert "<ITEM" not in bass
    assert len(tracks) == 4


def test_write_project_fails_with_no_stems(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        rp.write_reaper_project(empty / "song.RPP", empty, length_seconds=10)


def test_blocks_are_balanced(tmp_path):
    stems_dir = _stems(tmp_path)
    original = tmp_path / "song.wav"
    original.write_bytes(b"\0")
    text = rp.write_reaper_project(stems_dir / "song.RPP", stems_dir, original=original, length_seconds=10).read_text()
    opens = sum(1 for line in text.splitlines() if line.lstrip().startswith("<"))
    closes = sum(1 for line in text.splitlines() if line.strip() == ">")
    assert opens == closes
