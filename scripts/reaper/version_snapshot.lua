-- version_snapshot.lua
-- Riffkit: Save a timestamped backup of the current project file
--
-- Copies the .RPP file into a _snapshots/ subfolder next to the project and
-- adds a marker at the edit cursor with the snapshot timestamp.
--
-- Usage: Actions > Show Action List > Load ReaScript > select this file > Run

local r = reaper

local function path_sep()
  return package.config:sub(1, 1)
end

local function copy_file(src, dst)
  local fin = io.open(src, "rb")
  if not fin then return false, "cannot read: " .. src end
  local data = fin:read("*a")
  fin:close()
  local fout = io.open(dst, "wb")
  if not fout then return false, "cannot write: " .. dst end
  fout:write(data)
  fout:close()
  return true
end

local function ensure_dir(path)
  os.execute('mkdir -p "' .. path .. '"')
end

local function main()
  -- EnumProjects(-1) returns the current project's path
  local _, proj_file = r.EnumProjects(-1, "")

  if not proj_file or proj_file == "" then
    r.ShowMessageBox(
      "Project has not been saved yet.\nSave the project first, then run this script.",
      "Version Snapshot", 0)
    return
  end

  local sep      = path_sep()
  local proj_dir = proj_file:match("^(.*)" .. sep .. "[^" .. sep .. "]+$") or "."
  local snap_dir = proj_dir .. sep .. "_snapshots"
  ensure_dir(snap_dir)

  -- Build timestamped filename: ProjectName_2026-04-11_20-49-34.RPP
  local base = proj_file:match("([^" .. sep .. "]+)%.[Rr][Pp][Pp]$") or "project"
  local ts   = os.date("%Y-%m-%d_%H-%M-%S")
  local snap_name = base .. "_" .. ts .. ".RPP"
  local snap_path = snap_dir .. sep .. snap_name

  local ok, err = copy_file(proj_file, snap_path)
  if not ok then
    r.ShowMessageBox("Snapshot failed:\n" .. (err or "unknown error"), "Version Snapshot", 0)
    return
  end

  -- Add a marker at the edit cursor so the snapshot is visible on the timeline
  local pos = r.GetCursorPosition()
  r.AddProjectMarker2(0, false, pos, 0, "snapshot: " .. ts, -1, 0)
  r.UpdateTimeline()

  r.ShowConsoleMsg("[riffkit] Snapshot saved: " .. snap_path .. "\n")
  r.ShowMessageBox("Snapshot saved to _snapshots/:\n" .. snap_name, "Version Snapshot", 0)
end

main()
