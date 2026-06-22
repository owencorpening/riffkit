local json = {}

local function decode_error(str, pos, msg)
  error(string.format("%s at position %d near '%s'", msg, pos, str:sub(pos, pos + 20)), 0)
end

local function codepoint_to_utf8(codepoint)
  if utf8 and utf8.char then
    return utf8.char(codepoint)
  end

  if codepoint <= 0x7F then
    return string.char(codepoint)
  elseif codepoint <= 0x7FF then
    return string.char(
      0xC0 + math.floor(codepoint / 0x40),
      0x80 + (codepoint % 0x40)
    )
  elseif codepoint <= 0xFFFF then
    return string.char(
      0xE0 + math.floor(codepoint / 0x1000),
      0x80 + (math.floor(codepoint / 0x40) % 0x40),
      0x80 + (codepoint % 0x40)
    )
  elseif codepoint <= 0x10FFFF then
    return string.char(
      0xF0 + math.floor(codepoint / 0x40000),
      0x80 + (math.floor(codepoint / 0x1000) % 0x40),
      0x80 + (math.floor(codepoint / 0x40) % 0x40),
      0x80 + (codepoint % 0x40)
    )
  end

  decode_error("", 1, "Invalid Unicode codepoint")
end

local function parse_unicode_escape(str, pos)
  local hex = str:sub(pos, pos + 3)
  if not hex:match("^[0-9a-fA-F]+$") then
    decode_error(str, pos, "Invalid Unicode escape")
  end

  local codepoint = tonumber(hex, 16)
  pos = pos + 4

  if codepoint >= 0xD800 and codepoint <= 0xDBFF then
    if str:sub(pos, pos + 1) == "\\u" then
      local low_hex = str:sub(pos + 2, pos + 5)
      if low_hex:match("^[0-9a-fA-F]+$") then
        local low = tonumber(low_hex, 16)
        if low >= 0xDC00 and low <= 0xDFFF then
          codepoint = 0x10000 + ((codepoint - 0xD800) * 0x400) + (low - 0xDC00)
          pos = pos + 6
        end
      end
    end
  end

  return codepoint_to_utf8(codepoint), pos
end

function json.decode(str)
  local pos = 1

  local function skip_ws()
    while true do
      local c = str:sub(pos, pos)
      if c == "" or not c:match("%s") then
        return
      end
      pos = pos + 1
    end
  end

  local parse_value, parse_object, parse_array, parse_string, parse_number

  function parse_string()
    if str:sub(pos, pos) ~= '"' then
      decode_error(str, pos, "Expected string")
    end

    pos = pos + 1
    local parts = {}

    while true do
      local c = str:sub(pos, pos)
      if c == "" then
        decode_error(str, pos, "Unterminated string")
      elseif c == '"' then
        pos = pos + 1
        return table.concat(parts)
      elseif c == "\\" then
        pos = pos + 1
        local esc = str:sub(pos, pos)
        if esc == "" then
          decode_error(str, pos, "Unterminated escape sequence")
        end
        if esc == '"' or esc == "\\" or esc == "/" then
          parts[#parts + 1] = esc
          pos = pos + 1
        elseif esc == "b" then
          parts[#parts + 1] = "\b"
          pos = pos + 1
        elseif esc == "f" then
          parts[#parts + 1] = "\f"
          pos = pos + 1
        elseif esc == "n" then
          parts[#parts + 1] = "\n"
          pos = pos + 1
        elseif esc == "r" then
          parts[#parts + 1] = "\r"
          pos = pos + 1
        elseif esc == "t" then
          parts[#parts + 1] = "\t"
          pos = pos + 1
        elseif esc == "u" then
          local utf8_char
          utf8_char, pos = parse_unicode_escape(str, pos + 1)
          parts[#parts + 1] = utf8_char
        else
          decode_error(str, pos, "Invalid escape character")
        end
      else
        parts[#parts + 1] = c
        pos = pos + 1
      end
    end
  end

  function parse_number()
    local number_text = str:match("^%-?%d+%.?%d*[eE]?[+-]?%d*", pos)
    if not number_text or number_text == "" then
      decode_error(str, pos, "Invalid number")
    end
    pos = pos + #number_text
    local number_value = tonumber(number_text)
    if number_value == nil then
      decode_error(str, pos - #number_text, "Could not parse number")
    end
    return number_value
  end

  function parse_array()
    local result = {}
    pos = pos + 1
    skip_ws()
    if str:sub(pos, pos) == "]" then
      pos = pos + 1
      return result
    end

    while true do
      result[#result + 1] = parse_value()
      skip_ws()
      local c = str:sub(pos, pos)
      if c == "]" then
        pos = pos + 1
        return result
      elseif c ~= "," then
        decode_error(str, pos, "Expected ',' or ']' in array")
      end
      pos = pos + 1
      skip_ws()
    end
  end

  function parse_object()
    local result = {}
    pos = pos + 1
    skip_ws()
    if str:sub(pos, pos) == "}" then
      pos = pos + 1
      return result
    end

    while true do
      skip_ws()
      local key = parse_string()
      skip_ws()
      if str:sub(pos, pos) ~= ":" then
        decode_error(str, pos, "Expected ':' in object")
      end
      pos = pos + 1
      skip_ws()
      result[key] = parse_value()
      skip_ws()
      local c = str:sub(pos, pos)
      if c == "}" then
        pos = pos + 1
        return result
      elseif c ~= "," then
        decode_error(str, pos, "Expected ',' or '}' in object")
      end
      pos = pos + 1
      skip_ws()
    end
  end

  function parse_value()
    skip_ws()
    local c = str:sub(pos, pos)
    if c == '"' then
      return parse_string()
    elseif c == "{" then
      return parse_object()
    elseif c == "[" then
      return parse_array()
    elseif c == "-" or c:match("%d") then
      return parse_number()
    elseif str:sub(pos, pos + 3) == "true" then
      pos = pos + 4
      return true
    elseif str:sub(pos, pos + 4) == "false" then
      pos = pos + 5
      return false
    elseif str:sub(pos, pos + 3) == "null" then
      pos = pos + 4
      return nil
    end
    decode_error(str, pos, "Unexpected token")
  end

  local value = parse_value()
  skip_ws()
  if pos <= #str then
    decode_error(str, pos, "Trailing data after JSON value")
  end
  return value
end

return json
