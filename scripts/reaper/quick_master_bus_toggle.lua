-- quick_master_bus_toggle.lua
-- Riffkit: Toggle the master bus between production and rehearsal mode
--
-- Production mode: all master track FX are enabled (full mix chain).
-- Rehearsal mode:  all master track FX are bypassed (clean, low-latency output).
--
-- State is stored in project ExtState so it survives project reload.
-- Run this script a second time to toggle back.
--
-- Usage: Actions > Show Action List > Load ReaScript > select this file > Run

local r = reaper

local EXT_SECTION = "riffkit"
local EXT_KEY     = "master_bus_mode"

local function main()
  local master   = r.GetMasterTrack(0)
  local fx_count = r.TrackFX_GetCount(master)

  if fx_count == 0 then
    r.ShowMessageBox(
      "No FX found on the Master Track.\nAdd FX to the master bus first.",
      "Master Bus Toggle", 0)
    return
  end

  -- Read stored mode ("production" or "rehearsal"); default to production
  local _, stored = r.GetProjExtState(0, EXT_SECTION, EXT_KEY)
  local current   = (stored == "rehearsal") and "rehearsal" or "production"
  local next_mode = (current == "production") and "rehearsal" or "production"
  local enable    = (next_mode == "production")

  r.Undo_BeginBlock()

  for i = 0, fx_count - 1 do
    r.TrackFX_SetEnabled(master, i, enable)
  end

  r.SetProjExtState(0, EXT_SECTION, EXT_KEY, next_mode)
  r.Undo_EndBlock("Riffkit: Master Bus → " .. next_mode, -1)

  local label = enable and "PRODUCTION (FX on)" or "REHEARSAL (FX bypassed)"
  r.ShowConsoleMsg("[riffkit] Master bus: " .. label .. "\n")
end

main()
