"""Loop, line and speed math in karaoke-display/remote.html, run with Node.

The page keeps that math in <script id="loop-math">; these tests run that
script under Node and check the results. Skipped when Node isn't installed.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parent.parent / "karaoke-display" / "remote.html"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node is needed to run the page's JavaScript")


def math_script() -> str:
    m = re.search(r'<script id="loop-math">(.*?)</script>', PAGE.read_text(encoding="utf-8"), re.S)
    assert m, "remote.html has no <script id=\"loop-math\">"
    return m.group(1)


def js(expression: str):
    """Evaluate a JavaScript expression after the page's math script."""
    program = math_script() + f"\nprocess.stdout.write(JSON.stringify({expression}));\n"
    result = subprocess.run([NODE, "-e", program], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


# Made-up line times.
LINES = "[{start: 10, end: 14}, {start: 15, end: 19.5}, {start: 25, end: 28}]"


def test_speed_steps_by_five_percent_between_50_and_150():
    assert js("[stepRate(1, -1), stepRate(1, 1), stepRate(0.95, 1)]") == [0.95, 1.05, 1]
    assert js("[stepRate(0.5, -1), stepRate(1.5, 1)]") == [0.5, 1.5]
    assert js("Array.from({length: 12}, (_, i) => i).reduce((r) => stepRate(r, -1), 1)") == 0.5
    assert js("[rateLabel(0.9), rateLabel(1), rateLabel(1.15)]") == ["90%", "100%", "115%"]


def test_time_and_loop_labels():
    assert js("[formatTime(0), formatTime(72.9), formatTime(605)]") == ["0:00", "1:12", "10:05"]
    assert js("loopLabel({start: 72, end: 84})") == "Looping 1:12 to 1:24"
    assert js("loopLabel(null)") == "No loop"


def test_ab_loop_in_either_order_and_not_on_one_spot():
    assert js("abLoop(72, 84)") == {"start": 72, "end": 84}
    assert js("abLoop(84, 72)") == {"start": 72, "end": 84}
    assert js("abLoop(72, 72.05)") is None


def test_line_playing_now():
    assert js(f"[lineAt({LINES}, 5), lineAt({LINES}, 10), lineAt({LINES}, 14.5), lineAt({LINES}, 40)]") == [0, 0, 0, 2]
    assert js(f"lineAt({LINES}, 15.2)") == 1
    assert js("lineAt([], 3)") == -1


def test_line_loop_runs_from_first_start_to_last_end():
    assert js(f"lineLoop({LINES}, 1, 1)") == {"start": 15, "end": 19.5}
    assert js(f"lineLoop({LINES}, 0, 2)") == {"start": 10, "end": 28}


def test_plus_and_minus_line_stay_within_the_song_and_keep_one_line():
    assert js(f"addLine({LINES}, {{first: 0, last: 0}})") == {"first": 0, "last": 1}
    assert js(f"addLine({LINES}, {{first: 1, last: 2}})") == {"first": 1, "last": 2}
    assert js("removeLine({first: 1, last: 2})") == {"first": 1, "last": 1}
    assert js("removeLine({first: 1, last: 1})") == {"first": 1, "last": 1}


def test_lines_from_lyrics_json_skip_empty_lines_and_sort():
    doc = {"segments": [
        {"start": 9, "end": 12, "text": " second"},
        {"start": 2, "end": 5, "text": " first"},
        {"start": 6, "end": 7, "text": "  "},
    ]}
    assert js(f"linesFromDoc({json.dumps(doc)})") == [{"start": 2, "end": 5}, {"start": 9, "end": 12}]
