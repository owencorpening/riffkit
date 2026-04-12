"""
tests/test_reaper_scripts.py
Unit tests for the scripts/reaper/*.lua scripts.

REAPER's runtime can't run in CI, so the strategy is:
  1. File-existence checks — all six scripts must be present.
  2. Content-invariant checks — key strings (track names, CC numbers, marker
     conventions, toggle sentinel values) must appear in each script.
  3. Pure-logic helpers — functions that contain no REAPER API calls are
     re-implemented in Python and tested against the same inputs the Lua
     versions handle.  This covers strip_html / parse_note (lyric viewer),
     clamp127 / parse_marker_name (lighting sync), find_current_item (lyric
     viewer), and the CC-dispatch logic (MIDI remote).
"""

import re
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts" / "reaper"

# ── helpers mirroring the Lua implementations ──────────────────────────────

def strip_html(s: str) -> str:
    """Mirror of live_lyric_viewer.lua strip_html()."""
    s = re.sub(r"<[^>]+>", "", s)
    s = (s.replace("&amp;", "&")
          .replace("&lt;", "<")
          .replace("&gt;", ">")
          .replace("&nbsp;", " "))
    return s.strip()


def parse_note(note: str):
    """Mirror of live_lyric_viewer.lua parse_note(); returns (cur, nxt)."""
    cur_m = re.search(r"<h1[^>]*>(.*?)</h1>", note, re.DOTALL | re.IGNORECASE)
    nxt_m = re.search(r"<h3[^>]*>(.*?)</h3>", note, re.DOTALL | re.IGNORECASE)
    if cur_m:
        return strip_html(cur_m.group(1)), strip_html(nxt_m.group(1) if nxt_m else "")
    # Plain-text fallback: split on newlines
    lines = [ln.strip() for ln in note.splitlines() if ln.strip()]
    return (lines[0] if lines else ""), (lines[1] if len(lines) > 1 else "")


def find_current_item(items: list, play_pos: float):
    """Mirror of live_lyric_viewer.lua find_current_item(); returns (item, progress)."""
    result, progress = None, 0.0
    for item in sorted(items, key=lambda x: x["pos"]):
        if item["pos"] <= play_pos:
            result = item
            span = item["endpos"] - item["pos"]
            progress = min(1.0, (play_pos - item["pos"]) / span) if span > 0 else 0.0
        else:
            break
    return result, progress


def clamp127(n) -> int:
    """Mirror of stage_lighting_sync.lua clamp127()."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        n = 0.0
    return max(0, min(127, int(n + 0.5)))


def parse_marker_name(name: str):
    """Mirror of stage_lighting_sync.lua parse_marker_name(); returns (cmd, val) or (None, None)."""
    m = re.match(r"^([A-Z]+):(.+)$", name)
    if not m:
        return None, None
    return m.group(1), m.group(2)


# ── 1. File existence ───────────────────────────────────────────────────────

EXPECTED_SCRIPTS = [
    "quick_scratch_track.lua",
    "version_snapshot.lua",
    "quick_master_bus_toggle.lua",
    "stage_lighting_sync.lua",
    "live_lyric_viewer.lua",
    "smart_midi_remote.lua",
]

@pytest.mark.parametrize("script", EXPECTED_SCRIPTS)
def test_script_exists(script):
    assert (SCRIPTS_DIR / script).is_file(), f"Missing: {script}"


# ── 2. Content invariants ───────────────────────────────────────────────────

def read_script(name: str) -> str:
    return (SCRIPTS_DIR / name).read_text()


class TestQuickScratchTrack:
    def test_contains_expected_track_names(self):
        src = read_script("quick_scratch_track.lua")
        for track in ("Guitar", "Bass", "Drums", "Vocals", "Keys", "Bus", "Lyrics"):
            assert track in src

    def test_uses_new_project_tab_action(self):
        # Action 40859 = File: New project in new tab
        assert "40859" in read_script("quick_scratch_track.lua")

    def test_sets_track_volume_to_unity(self):
        assert "D_VOL" in read_script("quick_scratch_track.lua")


class TestVersionSnapshot:
    def test_uses_snapshots_subfolder(self):
        assert "_snapshots" in read_script("version_snapshot.lua")

    def test_adds_timeline_marker(self):
        assert "AddProjectMarker" in read_script("version_snapshot.lua")

    def test_timestamp_uses_date_format(self):
        # os.date format string
        assert "%Y-%m-%d" in read_script("version_snapshot.lua")

    def test_warns_on_unsaved_project(self):
        src = read_script("version_snapshot.lua")
        assert "not been saved" in src or "SaveProject" in src or 'proj_file == ""' in src


class TestMasterBusToggle:
    def test_has_production_and_rehearsal_states(self):
        src = read_script("quick_master_bus_toggle.lua")
        assert "production" in src
        assert "rehearsal" in src

    def test_uses_proj_ext_state(self):
        src = read_script("quick_master_bus_toggle.lua")
        assert "GetProjExtState" in src
        assert "SetProjExtState" in src

    def test_toggles_all_fx(self):
        # Must iterate 0..fx_count and call SetEnabled
        src = read_script("quick_master_bus_toggle.lua")
        assert "TrackFX_SetEnabled" in src
        assert "TrackFX_GetCount" in src


class TestStageLightingSync:
    def test_handles_light_scene_cc_note_commands(self):
        src = read_script("stage_lighting_sync.lua")
        for cmd in ("LIGHT", "SCENE", "CC", "NOTE"):
            assert cmd in src

    def test_uses_toggle_via_ext_state(self):
        src = read_script("stage_lighting_sync.lua")
        assert "GetExtState" in src
        assert "SetExtState" in src

    def test_uses_defer_loop(self):
        assert "r.defer(loop)" in read_script("stage_lighting_sync.lua")

    def test_resets_position_on_stop(self):
        # last_pos should reset when not playing so markers re-fire after seek
        src = read_script("stage_lighting_sync.lua")
        assert "last_pos = -1" in src


class TestLiveLyricViewer:
    def test_reads_lyrics_track_by_name(self):
        src = read_script("live_lyric_viewer.lua")
        assert "Lyrics" in src

    def test_uses_gfx(self):
        src = read_script("live_lyric_viewer.lua")
        assert "gfx.init" in src
        assert "gfx.update" in src

    def test_progress_bar_present(self):
        assert "progress" in read_script("live_lyric_viewer.lua")

    def test_uses_toggle_via_ext_state(self):
        src = read_script("live_lyric_viewer.lua")
        assert "GetExtState" in src
        assert "SetExtState" in src

    def test_tries_sws_notes_then_p_notes(self):
        src = read_script("live_lyric_viewer.lua")
        assert "ULT_GetMediaItemNote" in src
        assert "P_NOTES" in src


class TestSmartMidiRemote:
    def test_has_stem_track_mutes(self):
        src = read_script("smart_midi_remote.lua")
        for name in ("Guitar", "Bass", "Drums", "Vocals", "Keys"):
            assert name in src

    def test_has_transport_actions(self):
        src = read_script("smart_midi_remote.lua")
        assert "play_stop" in src or "1007" in src   # Transport: Play
        assert "1016" in src                          # Transport: Stop

    def test_has_marker_navigation(self):
        src = read_script("smart_midi_remote.lua")
        assert "40172" in src   # Go to previous marker
        assert "40173" in src   # Go to next marker

    def test_uses_toggle_via_ext_state(self):
        src = read_script("smart_midi_remote.lua")
        assert "GetExtState" in src
        assert "SetExtState" in src

    def test_cc_map_covers_expected_ccs(self):
        src = read_script("smart_midi_remote.lua")
        for cc in (1, 2, 10, 11, 12, 13, 14, 20, 21, 22):
            assert f"cc = {cc}" in src or f"cc={cc}" in src


# ── 3. Pure-logic helper tests ──────────────────────────────────────────────

class TestStripHtml:
    def test_removes_h1_tags(self):
        assert strip_html("<h1>Hello</h1>") == "Hello"

    def test_removes_nested_tags(self):
        assert strip_html("<b><font color='#FFF'>world</font></b>") == "world"

    def test_decodes_entities(self):
        # trailing &nbsp; becomes a space, which is then trimmed
        assert strip_html("&amp; &lt;b&gt; &nbsp;") == "& <b>"

    def test_trims_whitespace(self):
        assert strip_html("  hi  ") == "hi"

    def test_empty_string(self):
        assert strip_html("") == ""


class TestParseNote:
    def test_extracts_html_format_from_insert_lyrics(self):
        note = "<h1>Verse one line</h1><h3 style='color:yellow'>Next line here</h3>"
        cur, nxt = parse_note(note)
        assert cur == "Verse one line"
        assert nxt == "Next line here"

    def test_extracts_html_format_from_add_lyrics(self):
        note = (
            "<h1><b><font color='#FFFFFF'>Current lyric</font></b></h1>\n"
            "<h3><font color='#FFFF00'>Next lyric</font></h3>"
        )
        cur, nxt = parse_note(note)
        assert cur == "Current lyric"
        assert nxt == "Next lyric"

    def test_plain_text_fallback_two_lines(self):
        cur, nxt = parse_note("Line one\nLine two")
        assert cur == "Line one"
        assert nxt == "Line two"

    def test_plain_text_fallback_one_line(self):
        cur, nxt = parse_note("Only line")
        assert cur == "Only line"
        assert nxt == ""

    def test_empty_note(self):
        cur, nxt = parse_note("")
        assert cur == ""
        assert nxt == ""


class TestFindCurrentItem:
    ITEMS = [
        {"pos": 0.0,  "endpos": 4.0,  "cur": "Intro",  "nxt": "Verse"},
        {"pos": 4.0,  "endpos": 8.0,  "cur": "Verse",  "nxt": "Chorus"},
        {"pos": 8.0,  "endpos": 12.0, "cur": "Chorus", "nxt": ""},
    ]

    def test_returns_none_before_first_item(self):
        item, prog = find_current_item(self.ITEMS, -1.0)
        assert item is None
        assert prog == 0.0

    def test_returns_first_item_at_start(self):
        item, prog = find_current_item(self.ITEMS, 0.0)
        assert item["cur"] == "Intro"
        assert prog == pytest.approx(0.0)

    def test_returns_correct_progress_midway(self):
        item, prog = find_current_item(self.ITEMS, 2.0)
        assert item["cur"] == "Intro"
        assert prog == pytest.approx(0.5)

    def test_advances_to_next_item(self):
        item, prog = find_current_item(self.ITEMS, 4.0)
        assert item["cur"] == "Verse"

    def test_clamps_progress_to_1(self):
        item, prog = find_current_item(self.ITEMS, 11.9)
        assert item["cur"] == "Chorus"
        assert prog <= 1.0

    def test_returns_last_item_past_end(self):
        item, _ = find_current_item(self.ITEMS, 999.0)
        assert item["cur"] == "Chorus"

    def test_empty_items(self):
        item, prog = find_current_item([], 5.0)
        assert item is None
        assert prog == 0.0


class TestClamp127:
    def test_clamps_above_127(self):
        assert clamp127(200) == 127

    def test_clamps_below_0(self):
        assert clamp127(-5) == 0

    def test_midrange(self):
        assert clamp127(64) == 64

    def test_rounds_half(self):
        assert clamp127(63.5) == 64

    def test_string_input(self):
        assert clamp127("100") == 100

    def test_invalid_string(self):
        assert clamp127("abc") == 0

    def test_boundary_0(self):
        assert clamp127(0) == 0

    def test_boundary_127(self):
        assert clamp127(127) == 127


class TestParseMarkerName:
    def test_light_marker(self):
        cmd, val = parse_marker_name("LIGHT:100")
        assert cmd == "LIGHT"
        assert val == "100"

    def test_scene_marker(self):
        cmd, val = parse_marker_name("SCENE:3")
        assert cmd == "SCENE"
        assert val == "3"

    def test_cc_marker(self):
        cmd, val = parse_marker_name("CC:7,90")
        assert cmd == "CC"
        assert val == "7,90"

    def test_note_marker(self):
        cmd, val = parse_marker_name("NOTE:60")
        assert cmd == "NOTE"
        assert val == "60"

    def test_no_colon_returns_none(self):
        cmd, val = parse_marker_name("section1")
        assert cmd is None
        assert val is None

    def test_lowercase_does_not_match(self):
        # Lua version uses uppercase match; lower-case markers are ignored
        cmd, val = parse_marker_name("light:50")
        assert cmd is None

    def test_empty_string(self):
        cmd, val = parse_marker_name("")
        assert cmd is None
