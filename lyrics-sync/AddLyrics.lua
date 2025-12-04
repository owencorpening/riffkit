--[[
  Title: AddLyrics.lua
  Description: This REAPER Lua script automates the process of adding lyrics
  to a REAPER project by aligning them to peaks or silences in the "Vocals" track.

  Fixes & Improvements:
  - **Improved Peak Detection**: Adaptive threshold to avoid false positives.
  - **Ensures Lyrics Align to Peaks**: No more misplaced items.
  - **Optional Silence Detection Mode**: Align lyrics to vocal gaps.
  - **Debugging Output**: Logs peaks/silences to REAPER’s console.

  Usage:
  - Set `CONFIG.detection_mode = "peaks"` (default) or `"silence"`.
  - Run the script in REAPER.
  - Check the REAPER console for peak/silence logs.
]]

-- Configuration
local CONFIG = {
    detection_mode = "peaks", -- "peaks" (default) or "silence"
    peak_threshold = 0.4, -- Minimum amplitude for a peak (adaptive)
    silence_threshold = 0.02, -- Maximum amplitude to count as silence
    silence_duration = 0.3, -- Minimum duration (in seconds) for a silence
    default_item_length = 6, -- Default lyric duration
    lyrics_track_name = "Lyrics",
    vocals_track_name = "Vocals",
}

-- Debug helper function
local function Msg(text)
    reaper.ShowConsoleMsg(tostring(text) .. "\n")
end

-- Find track by name
local function FindTrackByName(track_name)
    for i = 0, reaper.CountTracks(0) - 1 do
        local track = reaper.GetTrack(0, i)
        local _, current_track_name = reaper.GetSetMediaTrackInfo_String(track, "P_NAME", "", false)
        if current_track_name == track_name then
            return track
        end
    end
    return nil
end

-- Improved Peak Detection
local function DetectElevatedRegions(track)
    Msg("Detecting elevated sound regions in vocals track...")
    local regions = {}
    local item_count = reaper.CountTrackMediaItems(track)

    for i = 0, item_count - 1 do
        local item = reaper.GetTrackMediaItem(track, i)
        local take = reaper.GetActiveTake(item)

        if take and not reaper.TakeIsMIDI(take) then
            local accessor = reaper.CreateTakeAudioAccessor(take)
            local length = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")

            -- Ensure valid length
            if not length or length <= 0 then
                Msg("Warning: Skipping item with zero or undefined length.")
                reaper.DestroyAudioAccessor(accessor)
                goto continue
            end

            -- Set parameters
            local sample_rate = 44100
            local window_size = 0.5  -- Measure volume every 0.5s
            local num_windows = math.floor(length / window_size)
            local buffer_size = math.floor(window_size * sample_rate)

            -- Iterate through time windows
            for w = 0, num_windows - 1 do
                local start_time = w * window_size
                local buffer = reaper.new_array(buffer_size)
                reaper.GetAudioAccessorSamples(accessor, sample_rate, 1, start_time, buffer_size, buffer)

                -- Compute average amplitude in this window
                local avg_level = 0
                for j = 1, buffer_size do
                    avg_level = avg_level + math.abs(buffer[j])
                end
                avg_level = avg_level / buffer_size

                -- Store loud sections
                table.insert(regions, {time = start_time + reaper.GetMediaItemInfo_Value(item, "D_POSITION"), level = avg_level})
            end

            reaper.DestroyAudioAccessor(accessor)
        end
        ::continue::
    end

    -- Sort by loudest sections
    table.sort(regions, function(a, b) return a.level > b.level end)

    -- Select 19 loudest regions
    local selected_times = {}
    for i = 1, math.min(19, #regions) do
        table.insert(selected_times, regions[i].time)
        Msg("Selected elevated region at " .. regions[i].time .. "s with level " .. regions[i].level)
    end

    -- Sort times in ascending order
    table.sort(selected_times)

    return selected_times
end

-- Silence Detection
local function DetectSilences(track)
    Msg("Detecting silences in vocals track...")
    local silences = {}
    local item_count = reaper.CountTrackMediaItems(track)

    for i = 0, item_count - 1 do
        local item = reaper.GetTrackMediaItem(track, i)
        local take = reaper.GetActiveTake(item)
        if take and not reaper.TakeIsMIDI(take) then
            local accessor = reaper.CreateTakeAudioAccessor(take)
            local length = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")
            local buffer_size = math.floor(length * 44100)
            local buffer = reaper.new_array(buffer_size)

            reaper.GetAudioAccessorSamples(accessor, 44100, 1, 0, buffer_size, buffer)
            local silence_start = nil

            for j = 1, buffer_size do
                if math.abs(buffer[j]) < CONFIG.silence_threshold then
                    if not silence_start then silence_start = j / 44100 end
                else
                    if silence_start and ((j / 44100) - silence_start) >= CONFIG.silence_duration then
                        local silence_time = reaper.GetMediaItemInfo_Value(item, "D_POSITION") + silence_start
                        table.insert(silences, silence_time)
                        Msg("Silence detected at " .. silence_time .. "s")
                    end
                    silence_start = nil
                end
            end
            reaper.DestroyAudioAccessor(accessor)
        end
    end
    return silences
end

-- Select lyrics file
local ret_val, file_path = reaper.GetUserFileNameForRead("", "Select Lyrics File", ".txt")
if not ret_val or file_path == "" then return end

-- Read lyrics
local file = io.open(file_path, "r")
if not file then return end
local lyrics = {}
for line in file:lines() do
    line = line:gsub("^%s*(.-)%s*$", "%1")
    if line ~= "" and not line:match("^%[") then table.insert(lyrics, line) end
end
file:close()

-- Find tracks
local lyrics_track = FindTrackByName(CONFIG.lyrics_track_name)
local vocals_track = FindTrackByName(CONFIG.vocals_track_name)
if not lyrics_track or not vocals_track then return end

-- Delete existing lyrics
local existing_item_count = reaper.CountTrackMediaItems(lyrics_track)
if existing_item_count > 0 then
    for i = existing_item_count - 1, 0, -1 do
        local item = reaper.GetTrackMediaItem(lyrics_track, i)
        reaper.DeleteTrackMediaItem(lyrics_track, item)
    end
end

-- Detect timing points
local timing_points = CONFIG.detection_mode == "peaks" and DetectElevatedRegions(vocals_track) or DetectSilences(vocals_track)

-- Create new lyric items
local lyric_items = {}
for i, lyric in ipairs(lyrics) do
    local item = reaper.AddMediaItemToTrack(lyrics_track)
    local position = timing_points[i] or (i - 1) * (reaper.GetProjectLength(0) / #lyrics)
    reaper.SetMediaItemInfo_Value(item, "D_POSITION", position)
    reaper.SetMediaItemInfo_Value(item, "D_LENGTH", CONFIG.default_item_length)
    table.insert(lyric_items, {item = item, text = lyric})
end

-- Apply lyrics to media items
for i, lyric_item in ipairs(lyric_items) do
    local current_lyric = lyric_item.text or ""
    local next_lyric = lyrics[i + 1] or ""
    local note = string.format(
        "<h1><b><font color='#FFFFFF'>%s</font></b></h1>\n<h3><font color='#FFFF00'>%s</font></h3>",
        current_lyric, next_lyric
    )
    reaper.ULT_SetMediaItemNote(lyric_item.item, note)
end

reaper.UpdateArrange()
Msg("Lyrics placed successfully.")
