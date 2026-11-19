#!/usr/bin/env python3
"""
Score riffkit lyrics transcripts against a hand-made key.

    .venv/bin/python scripts/compare_lyrics.py <key.txt> <transcript.json> [more .json]

key.txt is your own transcription of what is actually sung: one line per
sung line. Blank lines and lines starting with # are ignored.

Each transcript is riffkit lyrics output (the segments/words JSON that
lyrics-sync/transcribe_adaptive.py writes). All of its words are aligned to
all of the key's words, and each result is attributed back to a key line:

* correct:  the transcript has the key word
* wrong:    the transcript has a different word in its place
* missing:  the key word has no counterpart in the transcript
* invented: a transcript word with no counterpart in the key (counted on
            the key line it falls after)

A line PASSes when at least 90% of its key words are correct. Transcripts
sit side by side, one column each, so models can be compared line by line.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PASS_RATIO = 0.9

GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"

_WORD_RE = re.compile(r"[\w']+")


def normalize(text: str) -> list[str]:
    """Lowercase words with punctuation removed; apostrophes inside words stay."""
    words = []
    for token in _WORD_RE.findall(text.lower()):
        token = token.strip("'")
        if token:
            words.append(token)
    return words


def parse_key(text: str) -> list[tuple[str, list[str]]]:
    """(original line, normalized words) for each sung line in the key."""
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        words = normalize(line)
        if words:
            lines.append((line, words))
    return lines


def transcript_words(data: dict) -> list[str]:
    """Every word in a riffkit transcript, in order, normalized."""
    words: list[str] = []
    segments = data.get("segments")
    if segments:
        for seg in segments:
            seg_words = seg.get("words")
            if seg_words:
                for w in seg_words:
                    words += normalize(w.get("word", ""))
            else:
                words += normalize(seg.get("text", ""))
    else:
        for w in data.get("words") or []:
            words += normalize(w.get("word", ""))
    return words


@dataclass
class LineScore:
    total: int
    correct: int = 0
    wrong: int = 0
    missing: int = 0
    invented: int = 0

    @property
    def passed(self) -> bool:
        return self.correct >= PASS_RATIO * self.total


def score(key_lines: list[list[str]], words: list[str]) -> list[LineScore]:
    """Align ``words`` to the key and count results per key line."""
    key_words = [w for line in key_lines for w in line]
    line_of = [i for i, line in enumerate(key_lines) for _ in line]
    scores = [LineScore(total=len(line)) for line in key_lines]
    if not scores:
        return scores

    def after(k: int) -> int:
        """Key line that a transcript word inserted before key word k belongs to."""
        return line_of[k - 1] if k > 0 else 0

    matcher = difflib.SequenceMatcher(None, key_words, words, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i1, i2):
                scores[line_of[k]].correct += 1
        elif tag == "delete":
            for k in range(i1, i2):
                scores[line_of[k]].missing += 1
        elif tag == "insert":
            scores[after(i1)].invented += j2 - j1
        else:  # replace: pair words up, then the leftovers are missing or invented
            paired = min(i2 - i1, j2 - j1)
            for k in range(i1, i1 + paired):
                scores[line_of[k]].wrong += 1
            for k in range(i1 + paired, i2):
                scores[line_of[k]].missing += 1
            extra = (j2 - j1) - paired
            if extra:
                scores[line_of[i2 - 1]].invented += extra
    return scores


def _cell(s: LineScore) -> tuple[str, str]:
    """(plain text, color) for one table cell."""
    status = "PASS" if s.passed else "FAIL"
    text = f"{status} {s.correct}/{s.total}"
    errors = [f"{label}{n}" for label, n in (("w", s.wrong), ("m", s.missing), ("i", s.invented)) if n]
    if errors:
        text += " " + " ".join(errors)
    return text, GREEN if s.passed else RED


def render(key: list[tuple[str, list[str]]], names: list[str], results: list[list[LineScore]],
           line_width: int = 48) -> str:
    rows = []
    for li, (line, _) in enumerate(key):
        shown = line if len(line) <= line_width else line[: line_width - 3] + "..."
        rows.append((f"{li + 1:>3}  {shown}", [_cell(r[li]) for r in results]))

    first_width = max([len("Line")] + [len(r[0]) for r in rows])
    widths = [max([len(n)] + [len(r[1][c][0]) for r in rows]) for c, n in enumerate(names)]

    out = ["  ".join(["Line".ljust(first_width)] + [n.ljust(w) for n, w in zip(names, widths)])]
    out.append("  ".join(["-" * first_width] + ["-" * w for w in widths]))
    for first, cells in rows:
        parts = [first.ljust(first_width)]
        for (text, color), w in zip(cells, widths):
            parts.append(f"{color}{text.ljust(w)}{RESET}")
        out.append("  ".join(parts).rstrip())

    out.append("")
    out.append("w = wrong, m = missing, i = invented")
    out.append("")
    for name, scores in zip(names, results):
        total = sum(s.total for s in scores)
        correct = sum(s.correct for s in scores)
        errors = sum(s.wrong + s.missing + s.invented for s in scores)
        passed = sum(s.passed for s in scores)
        wer = errors / total if total else 0.0
        out.append(
            f"{name}: {correct}/{total} words correct, "
            f"word error rate {wer:.1%}, {passed}/{len(scores)} lines passed"
        )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score lyrics transcripts against a hand-made key.")
    parser.add_argument("key", type=Path, help="Your transcription: one sung line per line")
    parser.add_argument("transcripts", type=Path, nargs="+", help="riffkit lyrics JSON files")
    args = parser.parse_args(argv)

    key = parse_key(args.key.read_text(encoding="utf-8"))
    if not key:
        print(f"No sung lines in {args.key}", file=sys.stderr)
        return 1
    key_lines = [words for _, words in key]

    names, results = [], []
    for path in args.transcripts:
        data = json.loads(path.read_text(encoding="utf-8"))
        names.append(path.stem)
        results.append(score(key_lines, transcript_words(data)))

    print(render(key, names, results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
