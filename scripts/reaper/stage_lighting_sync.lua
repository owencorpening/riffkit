-- stage_lighting_sync.lua
-- Riffkit: Fire MIDI messages from timeline markers for lighting/video sync
--
-- Add markers to your project timeline named with this convention:
--
--   LIGHT:<0-127>   → MIDI CC 1 (Modulation) on ch 1  e.g. "LIGHT:100"
--   SCENE:<0-127>   → MIDI Program Change on ch 1      e.g. "SCENE:3"
--   CC:<cc>,<val>   → Arbitrary MIDI CC on ch 1        e.g. "CC:7,90"
--   NOTE:<note>     → MIDI Note On (vel 127) on ch 1   e.g. "NOTE:60"
--
-- MIDI is sent to REAPER's virtual keyboard input (mode 0), which routes
-- to any armed/monitoring track.  For hardware output, set a MIDI track to
-- monitor input and route its output to your lighting device.
--
-- Run this script to START the sync loop.  Run it again to STOP.
--
-- Usage: Actions > Show Action List > Load ReaScript > select this file > Run

local r = reaper

local EXT_SECTION = "riffkit_lighting"
local EXT_KEY     = "running"

-- ── MIDI helpers ───────────────────────────────────────────────────────────

local function clamp127(n)
  n = tonumber(n) or 0
  return math.max(0, math.min(127, math.floor(n + 0.5)))
end

local function send_midi(status, b1, b2)
  r.StuffMIDIMessage(0, status, b1, b2 or 0)
end

-- ── Marker parser ──────────────────────────────────────────────────────────

-- Returns true if the marker name matched and a MIDI message was sent
local function fire_marker(name)
  local cmd, args = name:match("^(%u+):(.+)$")
  if not cmd then return false end

  if cmd == "LIGHT" then
    send_midi(0xB0, 1, clamp127(args))            -- CC 1 on ch 1
    r.ShowConsoleMsg("[lighting] LIGHT CC1=" .. args .. "\n")

  elseif cmd == "SCENE" then
    send_midi(0xC0, clamp127(args), 0)            -- Program Change on ch 1
    r.ShowConsoleMsg("[lighting] SCENE PC=" .. args .. "\n")

  elseif cmd == "CC" then
    local cc, val = args:match("^(%d+),(%d+)$")
    if cc and val then
      send_midi(0xB0, clamp127(cc), clamp127(val))
      r.ShowConsoleMsg("[lighting] CC " .. cc .. "=" .. val .. "\n")
    end

  elseif cmd == "NOTE" then
    send_midi(0x90, clamp127(args), 127)          -- Note On vel 127 on ch 1
    r.ShowConsoleMsg("[lighting] NOTE " .. args .. "\n")

  else
    return false
  end

  return true
end

-- ── Marker list ────────────────────────────────────────────────────────────

local function collect_markers()
  local markers = {}
  local i = 0
  while true do
    local retval, is_region, pos, _, name = r.EnumProjectMarkers(i)
    if retval == 0 then break end
    if not is_region then
      table.insert(markers, { pos = pos, name = name })
    end
    i = i + 1
  end
  return markers
end

-- ── Main defer loop ────────────────────────────────────────────────────────

-- Toggle: if already running, signal stop and exit
if r.GetExtState(EXT_SECTION, EXT_KEY) == "1" then
  r.SetExtState(EXT_SECTION, EXT_KEY, "0", false)
  r.ShowConsoleMsg("[riffkit] Lighting sync stopped.\n")
  return
end

r.SetExtState(EXT_SECTION, EXT_KEY, "1", false)
r.ShowConsoleMsg("[riffkit] Lighting sync started. Run again to stop.\n")

local markers      = collect_markers()
local last_pos     = -1
local last_rebuild = r.time_precise()

local function loop()
  -- Stop if signaled
  if r.GetExtState(EXT_SECTION, EXT_KEY) ~= "1" then return end

  -- Rebuild marker list every 2 seconds (cheap, handles edits mid-session)
  local now = r.time_precise()
  if now - last_rebuild > 2 then
    markers      = collect_markers()
    last_rebuild = now
  end

  local play_state = r.GetPlayState()  -- 0=stopped, 1=playing, 2=paused, 5=recording

  if play_state == 1 then
    local pos = r.GetPlayPosition()
    if last_pos >= 0 then
      for _, m in ipairs(markers) do
        if m.pos > last_pos and m.pos <= pos then
          fire_marker(m.name)
        end
      end
    end
    last_pos = pos
  else
    last_pos = -1  -- reset so markers re-fire after stop/seek
  end

  r.defer(loop)
end

loop()
