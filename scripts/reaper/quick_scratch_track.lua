-- quick_scratch_track.lua
-- Riffkit: Create a new scratch project with standard tracks pre-loaded
--
-- Opens a new project tab with Guitar, Bass, Drums, Vocals, Keys, Bus, and
-- Lyrics tracks, each color-coded and set to unity gain.
--
-- Usage: Actions > Show Action List > Load ReaScript > select this file > Run

local r = reaper

local TRACKS = {
  { name = "Guitar", rv = 51,  g = 153, b = 255 },
  { name = "Bass",   rv = 255, g = 102, b = 51  },
  { name = "Drums",  rv = 255, g = 51,  b = 51  },
  { name = "Vocals", rv = 51,  g = 204, b = 102 },
  { name = "Keys",   rv = 255, g = 204, b = 0   },
  { name = "Bus",    rv = 180, g = 180, b = 180 },
  { name = "Lyrics", rv = 200, g = 200, b = 200 },
}

local function make_color(rv, g, b)
  -- ColorToNative returns a value < 0x1000000; adding the flag marks it as set
  return r.ColorToNative(rv, g, b) + 0x1000000
end

local function main()
  r.Main_OnCommand(40859, 0) -- File: New project in new tab

  r.Undo_BeginBlock()

  for i, t in ipairs(TRACKS) do
    r.InsertTrackAtIndex(i - 1, true)
    local track = r.GetTrack(0, i - 1)
    r.GetSetMediaTrackInfo_String(track, "P_NAME", t.name, true)
    r.SetTrackColor(track, make_color(t.rv, t.g, t.b))
    r.SetMediaTrackInfo_Value(track, "D_VOL", 1.0)   -- unity gain
    r.SetMediaTrackInfo_Value(track, "D_PAN", 0.0)   -- center
  end

  -- Set Bus track to receive sends from instrument tracks (Guitar–Keys)
  local bus_track = r.GetTrack(0, 5) -- "Bus" is index 5
  for i = 0, 4 do                    -- Guitar, Bass, Drums, Vocals, Keys
    local src = r.GetTrack(0, i)
    -- Remove default send to master, add send to Bus instead
    r.RemoveTrackSend(src, 0, 0)          -- remove first post-fader send (master)
    local send_idx = r.CreateTrackSend(src, bus_track)
    r.SetTrackSendInfo_Value(src, 0, send_idx, "D_VOL", 1.0)
  end

  r.Undo_EndBlock("Riffkit: Create Scratch Project", -1)
  r.TrackList_AdjustWindows(false)
  r.UpdateArrange()

  r.ShowConsoleMsg("[riffkit] Scratch project ready: " .. #TRACKS .. " tracks created.\n")
end

main()
