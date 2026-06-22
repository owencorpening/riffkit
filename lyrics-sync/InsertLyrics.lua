-- Add the current script directory to the package search path.
local script_dir = debug.getinfo(1, "S").source:match("@(.*[\\/])")
package.path = package.path .. ";" .. script_dir .. "?.lua"

local json = require("json")

reaper.ShowConsoleMsg("Starting Insert Lyrics Script...\n")

local function get_lyrics_track()
    for i = 0, reaper.CountTracks(0) - 1 do
        local track = reaper.GetTrack(0, i)
        local _, track_name = reaper.GetSetMediaTrackInfo_String(track, "P_NAME", "", false)
        if track_name == "Lyrics" then
            reaper.ShowConsoleMsg("Found track 'Lyrics'.\n")
            return track
        end
    end

    reaper.ShowConsoleMsg("Track 'Lyrics' not found.\n")
    return nil
end

local function read_json_file(file_path)
    reaper.ShowConsoleMsg("Opening JSON file: " .. file_path .. "\n")
    local file = io.open(file_path, "r")
    if not file then
        return nil, "Error opening file"
    end

    local content = file:read("*all")
    file:close()

    local ok, data = pcall(json.decode, content)
    if not ok then
        return nil, "Error parsing JSON: " .. tostring(data)
    end

    reaper.ShowConsoleMsg("JSON file parsed successfully.\n")
    return data
end

local function trim(text)
    return (text or ""):gsub("^%s+", ""):gsub("%s+$", "")
end

local function sanitize_lyric_text(text)
    text = trim(text)
    text = text:gsub("%s+", " ")
    return text
end

local function segment_is_terminal(text)
    return text:match("[%.%!%?]%s*$") ~= nil
end

local function normalize_timestamp_entry(entry)
    if type(entry) ~= "table" then
        return nil
    end

    local text = sanitize_lyric_text(entry.text or entry.word or entry.token or "")
    if text == "" then
        return nil
    end

    local start_seconds = entry.start or entry.begin or entry.from
    local end_seconds = entry["end"] or entry.finish or entry.to

    if entry.offsets then
        start_seconds = entry.offsets.from and (tonumber(entry.offsets.from) / 1000) or start_seconds
        end_seconds = entry.offsets.to and (tonumber(entry.offsets.to) / 1000) or end_seconds
    end

    start_seconds = tonumber(start_seconds)
    end_seconds = tonumber(end_seconds)

    if not start_seconds then
        return nil
    end

    if not end_seconds or end_seconds <= start_seconds then
        end_seconds = start_seconds + 0.5
    end

    return {
        text = text,
        start = start_seconds,
        finish = end_seconds,
    }
end

local function sort_entries(entries)
    table.sort(entries, function(a, b)
        if a.start == b.start then
            return (a.finish or a.start) < (b.finish or b.start)
        end
        return a.start < b.start
    end)
end

local function derive_entries_from_words(words)
    local entries = {}
    local current = nil

    local function flush_current()
        if current and current.text ~= "" then
            entries[#entries + 1] = current
        end
        current = nil
    end

    for _, word in ipairs(words) do
        local normalized = normalize_timestamp_entry(word)
        if normalized then
            local should_break = false
            if current then
                local gap = normalized.start - current.finish
                if gap > 0.8 then
                    should_break = true
                elseif current.word_count and current.word_count >= 10 then
                    should_break = true
                elseif current.char_count and current.char_count >= 60 then
                    should_break = true
                elseif segment_is_terminal(current.text) then
                    should_break = true
                end
            end

            if should_break then
                flush_current()
            end

            if not current then
                current = {
                    text = normalized.text,
                    start = normalized.start,
                    finish = normalized.finish,
                    word_count = 1,
                    char_count = #normalized.text,
                }
            else
                current.text = current.text .. " " .. normalized.text
                current.finish = normalized.finish
                current.word_count = current.word_count + 1
                current.char_count = current.char_count + 1 + #normalized.text
            end
        end
    end

    flush_current()
    return entries
end

local function extract_entries(transcript)
    if type(transcript) ~= "table" then
        return nil, "Transcript JSON did not decode into an object."
    end

    local entries = {}

    if type(transcript.transcription) == "table" then
        for _, entry in ipairs(transcript.transcription) do
            local normalized = normalize_timestamp_entry(entry)
            if normalized then
                entries[#entries + 1] = normalized
            end
        end
    elseif type(transcript.segments) == "table" then
        for _, entry in ipairs(transcript.segments) do
            local normalized = normalize_timestamp_entry(entry)
            if normalized then
                entries[#entries + 1] = normalized
            end
        end
    elseif type(transcript.words) == "table" then
        entries = derive_entries_from_words(transcript.words)
    else
        return nil, "The JSON file does not contain OpenAI `segments` or `words`, or legacy `transcription` data."
    end

    sort_entries(entries)
    return entries
end

local function insert_lyrics(entries)
    local track = get_lyrics_track()
    if not track then
        reaper.ShowMessageBox("No track named 'Lyrics' found.", "Error", 0)
        return
    end

    reaper.ShowConsoleMsg("Inserting formatted lyrics...\n")
    reaper.Undo_BeginBlock()

    for i, entry in ipairs(entries) do
        local lyric = entry.text
        local next_lyric = entries[i + 1] and entries[i + 1].text or ""
        local start = entry.start
        local finish = entry.finish
        local length = finish - start
        if length < 0.1 then
            length = 0.1
        end

        local formatted_lyrics = string.format(
            "<h1>%s</h1><h3 style='color:yellow'>%s</h3>",
            lyric,
            next_lyric
        )

        local item = reaper.AddMediaItemToTrack(track)
        reaper.SetMediaItemInfo_Value(item, "D_POSITION", start)
        reaper.SetMediaItemInfo_Value(item, "D_LENGTH", length)

        local take = reaper.AddTakeToMediaItem(item)
        if take then
            reaper.ULT_SetMediaItemNote(item, formatted_lyrics)
        else
            reaper.ShowConsoleMsg("Warning: Could not add take for entry " .. i .. "\n")
        end
    end

    reaper.Undo_EndBlock("Insert Formatted Lyrics", -1)
    reaper.ShowConsoleMsg("Finished inserting lyrics.\n")
end

local ret_val, file_path = reaper.GetUserFileNameForRead("", "Select OpenAI JSON File", "*.json")
if ret_val then
    local transcript, err = read_json_file(file_path)
    if transcript then
        local entries, extract_err = extract_entries(transcript)
        if entries then
            insert_lyrics(entries)
        else
            reaper.ShowMessageBox("Error: " .. extract_err, "Transcript Error", 0)
        end
    else
        reaper.ShowMessageBox("Error: " .. err, "File Error", 0)
    end
else
    reaper.ShowConsoleMsg("No file selected.\n")
end
