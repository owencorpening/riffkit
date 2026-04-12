-- smart_midi_remote.lua
-- Riffkit: Map MIDI controller inputs to riffkit live-performance actions
--
-- Designed for a smartphone/tablet running an OSC-to-MIDI or MIDI-over-network
-- app (e.g. TouchOSC, MIDI Designer, ZeroConf MIDI).
--
-- ── Default CC map (ch 1, customize below) ────────────────────────────────
--
--   CC 1  → Play / Stop toggle
--   CC 2  → Record toggle
--   CC 10 → Mute / unmute "Guitar" track
--   CC 11 → Mute / unmute "Bass" track
--   CC 12 → Mute / unmute "Drums" track
--   CC 13 → Mute / unmute "Vocals" track
--   CC 14 → Mute / unmute "Keys" track
--   CC 20 → Master volume (CC value mapped to 0–1 gain on master)
--   CC 21 → Seek to previous marker
--   CC 22 → Seek to next marker
--
-- Note On (any velocity) on the same channel triggers the same action as CC,
-- so pads and buttons work too.
--
-- ── REAPER MIDI input setup ────────────────────────────────────────────────
--   Options > Preferences > MIDI Devices → enable your controller as input.
--   The script reads from all enabled MIDI inputs.
--
-- Run this script to START listening.  Run it again to STOP.
--
-- Usage: Actions > Show Action List > Load ReaScript > select this file > Run

local r = reaper

local EXT_SECTION = "riffkit_remote"
local EXT_KEY     = "running"

local MIDI_CHANNEL = 1  -- 1-indexed; 0 = respond to all channels

-- ── Action handlers ────────────────────────────────────────────────────────

local function play_stop()
  local state = r.GetPlayState()
  if state == 1 or state == 5 then
    r.Main_OnCommand(1016, 0)  -- Transport: Stop
  else
    r.Main_OnCommand(1007, 0)  -- Transport: Play
  end
end

local function record_toggle()
  r.Main_OnCommand(1013, 0)    -- Transport: Record
end

local function mute_track(name)
  for i = 0, r.CountTracks(0) - 1 do
    local track = r.GetTrack(0, i)
    local _, tname = r.GetTrackName(track)
    if tname == name then
      local muted = r.GetMediaTrackInfo_Value(track, "B_MUTE")
      r.SetMediaTrackInfo_Value(track, "B_MUTE", muted == 0 and 1 or 0)
      r.ShowConsoleMsg("[remote] " .. name .. " mute → " .. (muted == 0 and "ON" or "OFF") .. "\n")
      return
    end
  end
  r.ShowConsoleMsg("[remote] track not found: " .. name .. "\n")
end

local function set_master_volume(cc_val)
  -- Map 0–127 → 0.0–1.0 gain (linear; 100 ≈ unity)
  local gain = cc_val / 100.0
  local master = r.GetMasterTrack(0)
  r.SetMediaTrackInfo_Value(master, "D_VOL", gain)
end

local function prev_marker()
  r.Main_OnCommand(40172, 0)   -- Markers: Go to previous marker/project start
end

local function next_marker()
  r.Main_OnCommand(40173, 0)   -- Markers: Go to next marker/project end
end

-- ── CC → action map ────────────────────────────────────────────────────────
-- Each entry: { cc = <number>, trigger = "any"|"high"|"low", action = <fn> }
-- "any"  = fire on every CC message for this number
-- "high" = fire only when value >= 64 (button press)
-- "low"  = fire only when value <  64 (button release)

local CC_MAP = {
  { cc = 1,  trigger = "high", action = play_stop },
  { cc = 2,  trigger = "high", action = record_toggle },
  { cc = 10, trigger = "high", action = function() mute_track("Guitar") end },
  { cc = 11, trigger = "high", action = function() mute_track("Bass")   end },
  { cc = 12, trigger = "high", action = function() mute_track("Drums")  end },
  { cc = 13, trigger = "high", action = function() mute_track("Vocals") end },
  { cc = 14, trigger = "high", action = function() mute_track("Keys")   end },
  { cc = 20, trigger = "any",  action = set_master_volume },
  { cc = 21, trigger = "high", action = prev_marker },
  { cc = 22, trigger = "high", action = next_marker },
}

-- Build a lookup table keyed by CC number for O(1) dispatch
local cc_lookup = {}
for _, entry in ipairs(CC_MAP) do
  cc_lookup[entry.cc] = entry
end

-- ── MIDI input polling ─────────────────────────────────────────────────────

local function dispatch(msg1, msg2, msg3)
  local status  = msg1 & 0xF0   -- strip channel
  local channel = (msg1 & 0x0F) + 1  -- 1-indexed

  -- Respect channel filter
  if MIDI_CHANNEL ~= 0 and channel ~= MIDI_CHANNEL then return end

  local is_cc   = (status == 0xB0)
  local is_note = (status == 0x90 and msg3 > 0)  -- Note On with velocity > 0

  if not (is_cc or is_note) then return end

  local cc_num = msg2
  local value  = msg3

  -- For Note On, treat note number as CC number and velocity as value
  local entry = cc_lookup[cc_num]
  if not entry then return end

  local trigger = entry.trigger
  local should_fire = (trigger == "any")
    or (trigger == "high" and value >= 64)
    or (trigger == "low"  and value < 64)

  if should_fire then
    if trigger == "any" then
      entry.action(value)
    else
      entry.action()
    end
  end
end

-- ── MIDI bus reader ────────────────────────────────────────────────────────
-- REAPER exposes a virtual MIDI bus via reaper.MIDI_GetRecentInputEvent

local last_msg_idx = -1

local function poll_midi()
  local i = 0
  while true do
    local ok, _, _, msg1, msg2, msg3, _ = r.MIDI_GetRecentInputEvent(i)
    if not ok then break end
    -- Skip messages we've already seen
    dispatch(msg1, msg2, msg3)
    i = i + 1
  end
end

-- ── Main defer loop ────────────────────────────────────────────────────────

if r.GetExtState(EXT_SECTION, EXT_KEY) == "1" then
  r.SetExtState(EXT_SECTION, EXT_KEY, "0", false)
  r.ShowConsoleMsg("[riffkit] MIDI remote stopped.\n")
  return
end

r.SetExtState(EXT_SECTION, EXT_KEY, "1", false)
r.ShowConsoleMsg("[riffkit] MIDI remote started (ch " ..
  (MIDI_CHANNEL == 0 and "all" or tostring(MIDI_CHANNEL)) .. "). Run again to stop.\n")

-- Print the active map
r.ShowConsoleMsg("  CC map:\n")
for _, e in ipairs(CC_MAP) do
  r.ShowConsoleMsg("    CC " .. e.cc .. " [" .. e.trigger .. "]\n")
end

local last_i     = 0
local last_stamp = 0

local function loop()
  if r.GetExtState(EXT_SECTION, EXT_KEY) ~= "1" then return end

  -- Poll recent MIDI input events; REAPER returns them newest-first at index 0
  -- We track the timestamp of the last processed event to avoid re-firing
  local i = 0
  while true do
    local ok, _, ts, msg1, msg2, msg3 = r.MIDI_GetRecentInputEvent(i)
    if not ok or ts == nil then break end
    if ts <= last_stamp then break end
    dispatch(msg1, msg2, msg3)
    i = i + 1
  end

  -- Update stamp from the most recent event (index 0)
  local ok, _, ts = r.MIDI_GetRecentInputEvent(0)
  if ok and ts then last_stamp = ts end

  r.defer(loop)
end

loop()
