-- live_lyric_viewer.lua
-- Riffkit: Floating teleprompter window that tracks the Lyrics track in real time
--
-- Reads media items from the "Lyrics" track (created by InsertLyrics.lua /
-- AddLyrics.lua).  Item notes are expected in the format written by those
-- scripts: <h1>current line</h1><h3 ...>next line</h3>
-- Plain-text notes also work fine.
--
-- The window shows:
--   • Current lyric line  — large white text, centred
--   • Next lyric line     — smaller yellow text, centred below
--   • A thin progress bar — tracks position within the current item
--
-- Run this script to OPEN the viewer.  Run it again (or close the window) to STOP.
--
-- Usage: Actions > Show Action List > Load ReaScript > select this file > Run

local r = reaper

local EXT_SECTION = "riffkit_lyrics"
local EXT_KEY     = "running"

local WIN_W, WIN_H = 900, 260
local FONT_MAIN    = 52
local FONT_NEXT    = 28
local BG_R, BG_G, BG_B = 0.05, 0.05, 0.05

-- ── helpers ────────────────────────────────────────────────────────────────

-- Strip basic HTML tags from a string
local function strip_html(s)
  if not s then return "" end
  s = s:gsub("<[^>]+>", "")
  s = s:gsub("&amp;",  "&")
  s = s:gsub("&lt;",   "<")
  s = s:gsub("&gt;",   ">")
  s = s:gsub("&nbsp;", " ")
  return s:match("^%s*(.-)%s*$") -- trim
end

-- Extract current and next lyric from an item note
local function parse_note(note)
  -- Try to pull h1 content (current) and h3 content (next)
  local cur  = note:match("<h1[^>]*>(.-)</h1>")
  local nxt  = note:match("<h3[^>]*>(.-)</h3>")
  if cur then
    return strip_html(cur), strip_html(nxt or "")
  end
  -- Fallback: plain text, split on newline
  local lines = {}
  for line in note:gmatch("[^\n]+") do
    local trimmed = line:match("^%s*(.-)%s*$")
    if trimmed ~= "" then table.insert(lines, trimmed) end
  end
  return lines[1] or "", lines[2] or ""
end

-- ── Lyrics track reader ────────────────────────────────────────────────────

local LYRICS_TRACK_NAME = "Lyrics"

local function find_lyrics_track()
  for i = 0, r.CountTracks(0) - 1 do
    local track = r.GetTrack(0, i)
    local _, name = r.GetTrackName(track)
    if name == LYRICS_TRACK_NAME then return track end
  end
  return nil
end

-- Returns a sorted list of { pos, endpos, cur, nxt } from the Lyrics track
local function load_lyric_items(track)
  local items = {}
  for i = 0, r.CountTrackMediaItems(track) - 1 do
    local item = r.GetTrackMediaItem(track, i)
    local pos  = r.GetMediaItemInfo_Value(item, "D_POSITION")
    local len  = r.GetMediaItemInfo_Value(item, "D_LENGTH")

    -- Try SWS ULT notes first, then fall back to P_NOTES
    local note = ""
    if r.ULT_GetMediaItemNote then
      note = r.ULT_GetMediaItemNote(item) or ""
    end
    if note == "" then
      local _, pn = r.GetSetMediaItemInfo_String(item, "P_NOTES", "", false)
      note = pn or ""
    end

    local cur, nxt = parse_note(note)
    table.insert(items, { pos = pos, endpos = pos + len, cur = cur, nxt = nxt })
  end
  table.sort(items, function(a, b) return a.pos < b.pos end)
  return items
end

-- Find which item the playhead is inside (or the most recent one before it)
local function find_current_item(items, play_pos)
  local result, progress = nil, 0
  for _, item in ipairs(items) do
    if item.pos <= play_pos then
      result = item
      local span = item.endpos - item.pos
      progress = span > 0 and math.min(1, (play_pos - item.pos) / span) or 0
    else
      break
    end
  end
  return result, progress
end

-- ── gfx drawing ────────────────────────────────────────────────────────────

local function draw_centred(text, y, font_idx)
  gfx.setfont(font_idx)
  local tw, th = gfx.measurestr(text)
  gfx.x = math.floor((gfx.w - tw) / 2)
  gfx.y = y
  gfx.drawstr(text)
  return th
end

local function draw_frame(cur_line, nxt_line, progress)
  -- Background
  gfx.r, gfx.g, gfx.b, gfx.a = BG_R, BG_G, BG_B, 1
  gfx.rect(0, 0, gfx.w, gfx.h, true)

  local pad = 20

  -- Current lyric (large white)
  gfx.r, gfx.g, gfx.b = 1, 1, 1
  local h1 = draw_centred(cur_line ~= "" and cur_line or "—", pad, 1)

  -- Next lyric (smaller yellow)
  gfx.r, gfx.g, gfx.b = 1, 1, 0.2
  draw_centred(nxt_line, pad + h1 + 14, 2)

  -- Progress bar (thin, at bottom)
  local bar_h = 4
  local bar_y = gfx.h - bar_h
  gfx.r, gfx.g, gfx.b = 0.2, 0.2, 0.2
  gfx.rect(0, bar_y, gfx.w, bar_h, true)
  gfx.r, gfx.g, gfx.b = 0.3, 0.8, 0.3
  gfx.rect(0, bar_y, math.floor(gfx.w * progress), bar_h, true)
end

-- ── Main defer loop ────────────────────────────────────────────────────────

-- Toggle: if already running, signal stop and exit
if r.GetExtState(EXT_SECTION, EXT_KEY) == "1" then
  r.SetExtState(EXT_SECTION, EXT_KEY, "0", false)
  r.ShowConsoleMsg("[riffkit] Lyric viewer stopped.\n")
  return
end

r.SetExtState(EXT_SECTION, EXT_KEY, "1", false)

gfx.init("Riffkit Lyric Viewer", WIN_W, WIN_H, 0)
gfx.setfont(1, "Arial", FONT_MAIN, string.byte("b"))
gfx.setfont(2, "Arial", FONT_NEXT, 0)

local lyric_items = {}
local last_rebuild = 0
local cur_line, nxt_line, progress = "", "", 0

local function loop()
  -- Stop conditions: flag cleared or window closed
  if r.GetExtState(EXT_SECTION, EXT_KEY) ~= "1" then
    gfx.quit()
    r.ShowConsoleMsg("[riffkit] Lyric viewer stopped.\n")
    return
  end
  if gfx.getchar() < 0 then  -- window was closed by user
    r.SetExtState(EXT_SECTION, EXT_KEY, "0", false)
    r.ShowConsoleMsg("[riffkit] Lyric viewer closed.\n")
    return
  end

  -- Rebuild lyric list every 3 seconds (handles edits and project switches)
  local now = r.time_precise()
  if now - last_rebuild > 3 then
    local track = find_lyrics_track()
    if track then
      lyric_items = load_lyric_items(track)
    end
    last_rebuild = now
  end

  local play_pos = r.GetPlayPosition()
  local item, prog = find_current_item(lyric_items, play_pos)

  cur_line = item and item.cur or ""
  nxt_line = item and item.nxt or ""
  progress = prog or 0

  draw_frame(cur_line, nxt_line, progress)
  gfx.update()

  r.defer(loop)
end

r.ShowConsoleMsg("[riffkit] Lyric viewer started. Run again (or close window) to stop.\n")
loop()
