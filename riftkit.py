#!/usr/bin/env python3
"""
riftkit: MP3 to practice-ready REAPER project

Usage:
    ./riftkit.py <song.mp3>
    ./riftkit.py <song.mp3> --output ~/music/projects
    ./riftkit.py <song.mp3> --no-lyrics

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
from pathlib import Path


TEMPLATE_RPP = Path(__file__).parent / "stem-separation" / "stem_template.RPP"
DEMUCS_MODEL = "htdemucs"  # 4-stem model: vocals, drums, bass, other


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

    args = parser.parse_args()

    audio_file = Path(args.audio_file).expanduser().resolve()
    if not audio_file.exists():
        print(f"Error: file not found: {audio_file}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nProcessing: {audio_file.name}")
    print(f"Output:     {output_dir}\n")

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
