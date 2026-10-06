--[[
Parse <out_dir>/<YYYY>/review.csv written by `stock-screening mark`.

Pure Lua 5.1 (no Lightroom APIs) so it can be unit-tested outside Lightroom.
The file is RFC 4180 CSV as written by Python's csv module: UTF-8, CRLF line endings,
fields quoted when they contain a comma, quote or newline (quotes doubled).
]]

local ReviewCsv = {}

ReviewCsv.DECISIONS = { "candidate", "review", "reject" }

local VALID_DECISION = {}
for _, d in ipairs(ReviewCsv.DECISIONS) do VALID_DECISION[d] = true end

-- Returns a list of rows, each a list of field strings. Raises an error on an unterminated quote.
function ReviewCsv.parseCsv(text)
	if text:sub(1, 3) == "\239\187\191" then -- UTF-8 BOM
		text = text:sub(4)
	end
	local rows, row = {}, {}
	local pos, n = 1, #text
	while pos <= n do
		local c = text:sub(pos, pos)
		local field
		if c == '"' then
			-- Quoted field: read up to the closing quote, un-doubling "".
			local parts, i = {}, pos + 1
			while true do
				local q = text:find('"', i, true)
				if not q then
					error("review.csv: unterminated quoted field (row " .. (#rows + 1) .. ")")
				end
				parts[#parts + 1] = text:sub(i, q - 1)
				if text:sub(q + 1, q + 1) == '"' then
					parts[#parts + 1] = '"'
					i = q + 2
				else
					pos = q + 1
					break
				end
			end
			field = table.concat(parts)
			-- Ignore anything between the closing quote and the next separator.
			local sep = text:find("[,\r\n]", pos)
			pos = sep or (n + 1)
		else
			local sep = text:find("[,\r\n]", pos)
			field = text:sub(pos, (sep or (n + 1)) - 1)
			pos = sep or (n + 1)
		end
		row[#row + 1] = field
		local s = text:sub(pos, pos)
		if s == "," then
			pos = pos + 1
			if pos > n then row[#row + 1] = "" end -- trailing comma at EOF
		else
			-- End of record (\r\n, \n, \r or EOF).
			if s == "\r" and text:sub(pos + 1, pos + 1) == "\n" then
				pos = pos + 2
			elseif s == "\r" or s == "\n" then
				pos = pos + 1
			end
			rows[#rows + 1] = row
			row = {}
		end
	end
	if #row > 0 then rows[#rows + 1] = row end -- last record ended with a comma at EOF
	return rows
end

local function trim(s)
	return (s:gsub("^%s+", ""):gsub("%s+$", ""))
end

-- "people;logo" -> "people, logo"
local function flagsText(s)
	local out = {}
	for flag in s:gmatch("[^;]+") do
		flag = trim(flag)
		if flag ~= "" then out[#out + 1] = flag end
	end
	return table.concat(out, ", ")
end

--[[
Parse review.csv text into records:
  { relpath=, decision=, flagsText=, note=, reviewedAt= }
relpath is unique: review.py writes the file from a dict keyed by relpath.
Returns records, warnings (list of strings). Raises an error if required columns are missing.
]]
function ReviewCsv.parseReview(text)
	local rows = ReviewCsv.parseCsv(text)
	if #rows == 0 then
		error("review.csv is empty")
	end
	local col = {}
	for i, name in ipairs(rows[1]) do
		col[trim(name)] = i
	end
	for _, required in ipairs({ "relpath", "decision" }) do
		if not col[required] then
			error("review.csv: missing column '" .. required .. "' (is this a stock-screening review.csv?)")
		end
	end
	local function get(row, name)
		local i = col[name]
		return i and row[i] or ""
	end

	local records, warnings = {}, {}
	for r = 2, #rows do
		local row = rows[r]
		if not (#row == 1 and row[1] == "") then -- skip blank lines
			local relpath = trim(get(row, "relpath"))
			local decision = trim(get(row, "decision"))
			if relpath == "" then
				warnings[#warnings + 1] = "row " .. r .. ": empty relpath, skipped"
			elseif not VALID_DECISION[decision] then
				warnings[#warnings + 1] = "row " .. r .. ": unknown decision '" .. decision .. "', skipped"
			else
				records[#records + 1] = {
					relpath = relpath,
					decision = decision,
					flagsText = flagsText(get(row, "flags")),
					note = get(row, "note"),
					reviewedAt = get(row, "reviewed_at"),
				}
			end
		end
	end
	return records, warnings
end

return ReviewCsv
