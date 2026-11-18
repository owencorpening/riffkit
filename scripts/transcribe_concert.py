#!/usr/bin/env python3
"""Transcribe a long concert recording with faster-whisper, in chunks.

Whole-file transcription of a 90-minute concert runs this machine out of
memory, so the audio is decoded once with ffmpeg and fed to the model in
fixed-length chunks. Timestamps are offset back to absolute concert time and
the JSON is rewritten after every chunk, so a crash loses at most one chunk.

Usage:
    .venv/bin/python scripts/transcribe_concert.py AUDIO OUTPUT.json \
        [--model small] [--chunk-minutes 10]
"""
import argparse
import json
import os
import subprocess
import time

import numpy as np
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # Windows: no symlinks without Developer Mode
from faster_whisper import WhisperModel  # noqa: E402

SR = 16000


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("audio", help="path to the audio file (anything ffmpeg can read)")
    ap.add_argument("output", help="path of the JSON transcript to write")
    ap.add_argument("--model", default="small", help="faster-whisper model name (default: small)")
    ap.add_argument("--chunk-minutes", type=float, default=10,
                    help="chunk length in minutes (default: 10)")
    args = ap.parse_args()
    if args.chunk_minutes <= 0:
        ap.error("--chunk-minutes must be greater than 0")

    chunk = int(args.chunk_minutes * 60 * SR)
    t0 = time.time()
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", args.audio, "-ac", "1", "-ar", str(SR),
         "-f", "f32le", "-"],
        capture_output=True, check=True).stdout
    samples = np.frombuffer(raw, dtype=np.float32)
    print(f"audio loaded: {len(samples) / SR / 60:.1f} minutes", flush=True)

    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    result = []
    for i in range(0, len(samples), chunk):
        off = i / SR
        segments, _info = model.transcribe(
            samples[i:i + chunk], language="en",
            word_timestamps=True, condition_on_previous_text=False)
        for s in segments:
            a, b = s.start + off, s.end + off
            print(f"[{int(a // 60):02d}:{a % 60:06.3f} --> {int(b // 60):02d}:{b % 60:06.3f}] {s.text}",
                  flush=True)
            result.append({
                "start": a, "end": b, "text": s.text,
                "words": [{"word": w.word, "start": w.start + off, "end": w.end + off}
                          for w in (s.words or [])],
            })
        with open(args.output, "w") as f:  # checkpoint after every chunk
            json.dump({"language": "en", "segments": result}, f)
    print(f"=== finished in {int(time.time() - t0)} seconds ===", flush=True)


if __name__ == "__main__":
    main()
