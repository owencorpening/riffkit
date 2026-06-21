from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


def sanitize_component(text: str) -> str:
    """Return a filesystem-safe path component."""
    cleaned = re.sub(r'[\\/:*?"<>|]', "_", text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "untitled"


def format_sortable_date(date_text: str | None) -> str:
    """Return a sortable date prefix suitable for folder names."""
    if not date_text:
        return "undated"

    value = date_text.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        if fmt == "%Y":
            return parsed.strftime("%Y")
        return parsed.strftime("%Y-%m-%d")
    return "undated"


def build_concert_folder_name(artist: str, concert_title: str, concert_date: str | None = None) -> str:
    """Build a sortable concert folder name."""
    date_prefix = format_sortable_date(concert_date)
    return " - ".join(
        [
            date_prefix,
            sanitize_component(artist),
            sanitize_component(concert_title),
        ]
    )


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_provenance_record(
    *,
    artist: str,
    concert_title: str,
    concert_date: str | None = None,
    source_title: str | None = None,
    source_url: str | None = None,
    source_audio: Path | None = None,
    source_text: Path | None = None,
    source_segments: Path | None = None,
    notes: str | None = None,
) -> dict:
    """Build a provenance manifest for a concert library entry."""
    now = datetime.now(timezone.utc).isoformat()
    source_assets = {}

    for label, path in (
        ("audio", source_audio),
        ("text", source_text),
        ("segments", source_segments),
    ):
        if path and path.exists():
            source_assets[label] = {
                "file": path.name,
                "sha256": sha256_file(path),
            }

    return {
        "schema": "riffkit.library.provenance.v1",
        "created_at": now,
        "artist": artist,
        "concert_title": concert_title,
        "concert_date": concert_date,
        "folder_name": build_concert_folder_name(artist, concert_title, concert_date),
        "source": {
            "title": source_title,
            "url": source_url,
        },
        "assets": source_assets,
        "notes": notes or "",
    }


def import_split_concert_to_library(
    *,
    split_dir: Path,
    library_root: Path,
    artist: str,
    concert_title: str,
    concert_date: str | None = None,
    source_title: str | None = None,
    source_url: str | None = None,
    source_text: Path | None = None,
    notes: str | None = None,
) -> Path:
    """Copy a split concert directory into a personal library layout."""
    manifest_path = split_dir / "segments.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing segments.json in {split_dir}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    concert_dir = library_root / "concerts" / build_concert_folder_name(
        artist,
        concert_title,
        concert_date,
    )
    source_dir = concert_dir / "source"
    songs_dir = concert_dir / "songs"
    source_dir.mkdir(parents=True, exist_ok=True)
    songs_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(manifest_path, source_dir / "segments.json")
    if source_text and source_text.exists():
        shutil.copy2(source_text, source_dir / source_text.name)

    for entry in manifest:
        src_file = split_dir / entry["file"]
        if not src_file.exists():
            raise FileNotFoundError(f"Missing split file: {src_file}")

        song_dir = songs_dir / f'{entry["index"]:02d} - {sanitize_component(entry["title"])}'
        song_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, song_dir / "audio.mp3")

    provenance = build_provenance_record(
        artist=artist,
        concert_title=concert_title,
        concert_date=concert_date,
        source_title=source_title,
        source_url=source_url,
        source_text=source_text,
        source_segments=manifest_path,
        notes=notes,
    )
    (concert_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return concert_dir
