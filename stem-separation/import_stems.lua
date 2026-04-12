-- import_stems.lua
-- Riffkit: Auto-import Demucs/UVR stems into a REAPER project
--
-- Usage:
--   1. Open stem_template.RPP (or any project with tracks named Vocals/Drums/Bass/Other)
--   2. Actions > Show Action List > Load ReaScript > select this file > Run
--   3. Pick any one stem file from your stems folder when prompted
--      (the whole folder will be scanned automatically)

local r = reaper

-- Stem filename keywords → target track name
-- First match wins, so order matters (e.g. "bass" before "other")
local STEM_MAP = {
  { keywords = { "vocals", "vocal", "vox", "voice", "singing" }, track = "Vocals" },
  { keywords = { "drums", "drum", "percussion", "perc" },         track = "Drums"  },
  { keywords = { "bass" },                                         track = "Bass"   },
  { keywords = { "other", "guitar", "gtr", "keys", "piano",
                 "melody", "instrument", "accompaniment" },        track = "Other"  },
}

local AUDIO_EXTS = { wav = true, mp3 = true, flac = true, aiff = true, ogg = true }

-- Returns the track whose name matches (case-insensitive), or nil
local function find_track_by_name(name)
  for i = 0, r.CountTracks(0) - 1 do
    local track = r.GetTrack(0, i)
    local _, track_name = r.GetTrackName(track)
    if track_name:lower() == name:lower() then
      return track
    end
  end
  return nil
end

-- Maps a bare filename (no path) to a track name from STEM_MAP, or nil
local function resolve_track_name(filename)
  local base = filename:match("^(.+)%.[^%.]+$") or filename
  base = base:lower()
  for _, entry in ipairs(STEM_MAP) do
    for _, kw in ipairs(entry.keywords) do
      if base == kw or base:find(kw, 1, true) then
        return entry.track
      end
    end
  end
  return nil
end

-- Insert a file at position 0 on the given track
local function insert_stem(filepath, track)
  r.SetOnlyTrackSelected(track)
  r.SetEditCurPos(0, false, false)
  r.InsertMedia(filepath, 0)
end

-- Returns a list of audio filenames in folder
local function scan_folder(folder)
  local files = {}
  local i = 0
  repeat
    local name = r.EnumerateFiles(folder, i)
    if name then
      local ext = name:match("%.([^%.]+)$")
      if ext and AUDIO_EXTS[ext:lower()] then
        table.insert(files, name)
      end
      i = i + 1
    end
  until not name
  return files
end

local function path_sep()
  return package.config:sub(1, 1) -- "/" on Unix, "\" on Windows
end

local function main()
  if r.CountTracks(0) == 0 then
    r.ShowMessageBox(
      "No tracks in the current project.\nOpen stem_template.RPP first, then run this script.",
      "Import Stems", 0)
    return
  end

  -- Ask user to pick one stem file; derive the folder from it
  local ok, filepath = r.GetUserFileNameForRead(
    "", "Select any stem file from your stems folder", "wav")
  if not ok or filepath == "" then return end

  local sep = path_sep()
  local folder = filepath:match("^(.*)" .. sep .. "[^" .. sep .. "]+$")
  if not folder then
    r.ShowMessageBox("Could not determine folder from:\n" .. filepath, "Import Stems", 0)
    return
  end

  local files = scan_folder(folder)
  if #files == 0 then
    r.ShowMessageBox("No audio files found in:\n" .. folder, "Import Stems", 0)
    return
  end

  local imported, skipped = {}, {}

  r.Undo_BeginBlock()
  r.PreventUIRefresh(1)

  for _, filename in ipairs(files) do
    local track_name = resolve_track_name(filename)
    if track_name then
      local track = find_track_by_name(track_name)
      if track then
        insert_stem(folder .. sep .. filename, track)
        table.insert(imported, filename .. "  →  " .. track_name)
      else
        table.insert(skipped, filename .. "  (no track named '" .. track_name .. "')")
      end
    else
      table.insert(skipped, filename .. "  (unrecognized name)")
    end
  end

  r.PreventUIRefresh(-1)
  r.UpdateArrange()
  r.Undo_EndBlock("Import Stems", -1)

  local lines = { "Imported " .. #imported .. " stem(s):" }
  for _, s in ipairs(imported) do table.insert(lines, "  " .. s) end
  if #skipped > 0 then
    table.insert(lines, "")
    table.insert(lines, "Skipped " .. #skipped .. ":")
    for _, s in ipairs(skipped) do table.insert(lines, "  " .. s) end
  end
  r.ShowMessageBox(table.concat(lines, "\n"), "Import Stems", 0)
end

main()