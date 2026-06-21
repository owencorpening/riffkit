import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import riftkit
import library_tools

FIXTURES_DIR = Path(__file__).parent / "fixtures"
STOCKHOLM_AUDIO = FIXTURES_DIR / "audio" / "stockholm_excerpt.mp3"
STOCKHOLM_LYRICS = FIXTURES_DIR / "lyrics" / "stockholm_excerpt.txt"
STOCKHOLM_SPLIT_DIR = FIXTURES_DIR / "stockholm_split"


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
# concert splitting
# ---------------------------------------------------------------------------

def test_build_song_segments_from_silences():
    segments = riftkit.build_song_segments(
        300.0,
        [(55.0, 70.0), (150.0, 168.0), (240.0, 252.0)],
    )

    assert segments == [
        (0.0, 55.0),
        (70.0, 150.0),
        (168.0, 240.0),
        (252.0, 300.0),
    ]


def test_parse_song_titles_from_sidecar(tmp_path):
    song_list = tmp_path / "concert.txt"
    song_list.write_text(
        "Jimi Hendrix - Live\n"
        "Date: September 03, 1970\n"
        "\n"
        "Songs:\n"
        "Stone Free\n"
        "Foxy Lady\n"
        "1. Hey Baby\n"
        "02) All Along The Watchtower\n",
        encoding="utf-8",
    )

    assert riftkit.parse_song_titles(song_list) == [
        "Stone Free",
        "Foxy Lady",
        "Hey Baby",
        "All Along The Watchtower",
    ]


def test_parse_song_titles_from_leading_block(tmp_path):
    song_list = tmp_path / "concert.txt"
    song_list.write_text(
        "Fire\n"
        "Spanish Castle Magic\n"
        "Machine Gun\n"
        "\n"
        "Jimi Hendrix - Live in Stockholm (1970)\n"
        "Date: April 26, 1970.\n",
        encoding="utf-8",
    )

    assert riftkit.parse_song_titles(song_list) == [
        "Fire",
        "Spanish Castle Magic",
        "Machine Gun",
    ]


def test_parse_song_cues_from_timestamped_sidecar(tmp_path):
    assert riftkit.parse_song_cues(STOCKHOLM_LYRICS) == [
        (0.0, "Introduction"),
        (70.0, "Fire Part 1"),
        (212.0, "Drum Solo"),
        (422.0, "Fire Part 2"),
        (536.0, "Spanish Castle Magic"),
    ]


def test_sanitize_filename_replaces_bad_chars():
    assert riftkit.sanitize_filename("A/B:C*D?E\"F<G>H|I") == "A_B_C_D_E_F_G_H_I"


def test_main_split_concert_invokes_splitter(tmp_path):
    audio = tmp_path / "concert.mp3"
    audio.touch()

    out_dir = tmp_path / "out"

    with patch("sys.argv", ["riftkit.py", str(audio), "--output", str(out_dir), "--split-concert"]), \
         patch.object(riftkit, "split_concert_into_songs") as mock_split:
        riftkit.main()

    mock_split.assert_called_once()
    called_audio, called_output = mock_split.call_args.args[:2]
    assert called_audio == audio.resolve()
    assert called_output == out_dir.resolve()


def test_split_concert_into_songs_writes_manifest(tmp_path):
    audio = tmp_path / "concert.mp3"
    audio.touch()
    out_dir = tmp_path / "out"

    with patch.object(riftkit, "probe_duration", return_value=300.0), \
         patch.object(riftkit, "detect_silence_intervals", return_value=[(55.0, 70.0), (150.0, 168.0)]), \
         patch.object(riftkit, "export_segment") as mock_export:
        split_dir = riftkit.split_concert_into_songs(audio, out_dir)

    assert split_dir == out_dir / "concert_songs"
    manifest = json.loads((split_dir / "segments.json").read_text())
    assert manifest == [
        {"index": 1, "file": "01 - song_01.mp3", "title": "song_01", "start_seconds": 0.0, "end_seconds": 55.0},
        {"index": 2, "file": "02 - song_02.mp3", "title": "song_02", "start_seconds": 70.0, "end_seconds": 150.0},
        {"index": 3, "file": "03 - song_03.mp3", "title": "song_03", "start_seconds": 168.0, "end_seconds": 300.0},
    ]
    assert mock_export.call_count == 3


def test_split_concert_into_songs_uses_titles(tmp_path):
    audio = tmp_path / "concert.mp3"
    audio.touch()
    out_dir = tmp_path / "out"
    titles = ["Stone Free", "Foxy Lady", "Hey Baby"]

    with patch.object(riftkit, "probe_duration", return_value=300.0), \
         patch.object(riftkit, "detect_silence_intervals", return_value=[(55.0, 70.0), (150.0, 168.0)]), \
         patch.object(riftkit, "export_segment"):
        split_dir = riftkit.split_concert_into_songs(audio, out_dir, song_titles=titles)

    manifest = json.loads((split_dir / "segments.json").read_text())
    assert manifest[0]["file"] == "01 - Stone Free.mp3"
    assert manifest[0]["title"] == "Stone Free"
    assert manifest[2]["file"] == "03 - Hey Baby.mp3"


def test_split_concert_into_songs_uses_timestamp_cues(tmp_path):
    audio = tmp_path / "concert.mp3"
    audio.touch()
    out_dir = tmp_path / "out"
    cues = [(12.0, "Intro"), (55.0, "Stone Free"), (150.0, "Foxy Lady")]

    with patch.object(riftkit, "probe_duration", return_value=300.0), \
         patch.object(riftkit, "export_segment") as mock_export:
        split_dir = riftkit.split_concert_into_songs(audio, out_dir, song_cues=cues)

    assert split_dir == out_dir / "concert_songs"
    manifest = json.loads((split_dir / "segments.json").read_text())
    assert manifest == [
        {"index": 1, "file": "01 - Intro.mp3", "title": "Intro", "start_seconds": 12.0, "end_seconds": 55.0},
        {"index": 2, "file": "02 - Stone Free.mp3", "title": "Stone Free", "start_seconds": 55.0, "end_seconds": 150.0},
        {"index": 3, "file": "03 - Foxy Lady.mp3", "title": "Foxy Lady", "start_seconds": 150.0, "end_seconds": 300.0},
    ]
    assert mock_export.call_count == 3


def test_main_split_concert_prefers_timestamp_cues(tmp_path):
    audio = tmp_path / "concert.mp3"
    audio.touch()
    song_list = tmp_path / "concert.txt"
    song_list.write_text("00:00 Intro\n00:45 Stone Free\n", encoding="utf-8")

    out_dir = tmp_path / "out"

    with patch("sys.argv", ["riftkit.py", str(audio), "--output", str(out_dir), "--split-concert"]), \
         patch.object(riftkit, "split_concert_into_songs") as mock_split:
        riftkit.main()

    mock_split.assert_called_once()
    kwargs = mock_split.call_args.kwargs
    assert kwargs["song_cues"] == [(0.0, "Intro"), (45.0, "Stone Free")]
    assert kwargs["song_titles"] == []


def test_stockholm_fixture_pair_is_parseable():
    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe is required for the Stockholm fixture smoke test")

    cues = riftkit.parse_song_cues(STOCKHOLM_LYRICS)
    duration = riftkit.probe_duration(STOCKHOLM_AUDIO)

    assert len(cues) == 5
    assert duration > 590.0
    assert cues[0] == (0.0, "Introduction")
    assert cues[-1] == (536.0, "Spanish Castle Magic")


def test_stockholm_split_fixture_matches_manifest():
    manifest = json.loads((STOCKHOLM_SPLIT_DIR / "segments.json").read_text())

    assert manifest[:3] == [
        {
            "index": 1,
            "file": "01 - Introduction.mp3",
            "title": "Introduction",
            "start_seconds": 0.0,
            "end_seconds": 70.0,
        },
        {
            "index": 2,
            "file": "02 - Fire Part 1.mp3",
            "title": "Fire Part 1",
            "start_seconds": 70.0,
            "end_seconds": 212.0,
        },
        {
            "index": 3,
            "file": "03 - Drum Solo.mp3",
            "title": "Drum Solo",
            "start_seconds": 212.0,
            "end_seconds": 422.0,
        },
    ]

    for entry in manifest[:3]:
        assert (STOCKHOLM_SPLIT_DIR / entry["file"]).is_file()
        assert (STOCKHOLM_SPLIT_DIR / entry["file"]).stat().st_size > 0


# ---------------------------------------------------------------------------
# library layout
# ---------------------------------------------------------------------------

def test_build_concert_folder_name_is_sortable():
    name = library_tools.build_concert_folder_name(
        "Jimi Hendrix",
        "Live in Stockholm (1970)",
        "1970-04-26",
    )

    assert name == "1970-04-26 - Jimi Hendrix - Live in Stockholm (1970)"


def test_build_provenance_record_hashes_source_files(tmp_path):
    audio = tmp_path / "concert.mp3"
    text = tmp_path / "concert.txt"
    segments = tmp_path / "segments.json"
    audio.write_bytes(b"audio-bytes")
    text.write_text("00:00 Intro\n", encoding="utf-8")
    segments.write_text("[]", encoding="utf-8")

    record = library_tools.build_provenance_record(
        artist="Jimi Hendrix",
        concert_title="Live in Stockholm (1970)",
        concert_date="1970-04-26",
        source_title="Jimi Hendrix - Live in Stockholm (1970) - Full Album",
        source_url="https://www.youtube.com/watch?v=example",
        source_audio=audio,
        source_text=text,
        source_segments=segments,
    )

    assert record["schema"] == "riffkit.library.provenance.v1"
    assert record["folder_name"] == "1970-04-26 - Jimi Hendrix - Live in Stockholm (1970)"
    assert record["source"]["url"] == "https://www.youtube.com/watch?v=example"
    assert record["assets"]["audio"]["file"] == "concert.mp3"
    assert len(record["assets"]["audio"]["sha256"]) == 64


def test_import_split_concert_to_library_creates_song_folders(tmp_path):
    split_dir = tmp_path / "split"
    split_dir.mkdir()
    (split_dir / "segments.json").write_text(
        json.dumps([
            {"index": 1, "file": "01 - Intro.mp3", "title": "Intro", "start_seconds": 0.0, "end_seconds": 45.0},
            {"index": 2, "file": "02 - Song Two.mp3", "title": "Song Two", "start_seconds": 45.0, "end_seconds": 90.0},
        ]),
        encoding="utf-8",
    )
    (split_dir / "01 - Intro.mp3").write_bytes(b"one")
    (split_dir / "02 - Song Two.mp3").write_bytes(b"two")

    source_text = tmp_path / "source.txt"
    source_text.write_text("00:00 Intro\n00:45 Song Two\n", encoding="utf-8")

    library_root = tmp_path / "music"
    concert_dir = library_tools.import_split_concert_to_library(
        split_dir=split_dir,
        library_root=library_root,
        artist="Test Artist",
        concert_title="Test Concert",
        concert_date="2026-06-21",
        source_title="Test Artist - Test Concert",
        source_url="https://www.youtube.com/watch?v=test",
        source_text=source_text,
    )

    assert concert_dir == library_root / "concerts" / "2026-06-21 - Test Artist - Test Concert"
    assert (concert_dir / "provenance.json").exists()
    assert (concert_dir / "source" / "segments.json").exists()
    assert (concert_dir / "source" / "source.txt").exists()
    assert (concert_dir / "songs" / "01 - Intro" / "audio.mp3").read_bytes() == b"one"
    assert (concert_dir / "songs" / "02 - Song Two" / "audio.mp3").read_bytes() == b"two"


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
