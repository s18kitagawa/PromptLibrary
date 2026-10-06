-- Unit tests for the Lightroom-independent modules of StockScreening.lrplugin.
-- Run from the repository root:  lua lightroom/tests/test_pure.lua
-- (Lua 5.1 - 5.4; Lightroom itself runs Lua 5.1.)

local here = arg and arg[0] and arg[0]:match("^(.*)/[^/]*$") or "."
package.path = here .. "/../StockScreening.lrplugin/?.lua;" .. package.path

local ReviewCsv = require "ReviewCsv"
local PathMatch = require "PathMatch"

local failures, total = 0, 0
local function check(name, cond, detail)
	total = total + 1
	if not cond then
		failures = failures + 1
		print("FAIL " .. name .. (detail and (": " .. detail) or ""))
	end
end
local function eq(name, got, want)
	check(name, got == want, string.format("got %q, want %q", tostring(got), tostring(want)))
end

-- CSV ------------------------------------------------------------------------

local rows = ReviewCsv.parseCsv('a,b,c\r\n1,"x, y","say ""hi"""\r\n,,\r\n')
eq("csv rows", #rows, 3)
eq("csv quoted comma", rows[2][2], "x, y")
eq("csv doubled quote", rows[2][3], 'say "hi"')
eq("csv empty fields", #rows[3], 3)
eq("csv empty field value", rows[3][3], "")

rows = ReviewCsv.parseCsv('h\n"line1\r\nline2"\n')
eq("csv embedded newline", rows[2][1], "line1\r\nline2")

rows = ReviewCsv.parseCsv("\239\187\191h1,h2\nv1,v2")
eq("csv bom stripped", rows[1][1], "h1")
eq("csv no trailing newline", rows[2][2], "v2")

rows = ReviewCsv.parseCsv("a,\n")
eq("csv trailing empty field", #rows[1], 2)

check("csv unterminated quote errors", not pcall(ReviewCsv.parseCsv, 'a\n"oops\n'))

-- review.csv ---------------------------------------------------------------

local text = table.concat({
	"relpath,id,decision,flags,note,reviewed_at",
	"2019/京都/DSC0001.ARW,0001,candidate,,,2026-10-06T10:00:00",
	'Trips/x/IMG_2.jpg,0002,review,people;logo,"faces, logo ""ABC""",2026-10-06T10:01:00',
	"a/b.dng,0003,reject,,,2026-10-06T10:02:00",
	"a/c.dng,0004,maybe,,,",
	",0005,candidate,,,",
	"a/b.dng,0003,candidate,,,2026-10-06T11:00:00",
	"",
}, "\r\n")
local recs, warns = ReviewCsv.parseReview(text)
eq("review count", #recs, 3)
eq("review warnings", #warns, 3)
eq("review utf8 relpath", recs[1].relpath, "2019/京都/DSC0001.ARW")
eq("review decision", recs[2].decision, "review")
eq("review flags list", #recs[2].flags, 2)
eq("review flags text", recs[2].flagsText, "people, logo")
eq("review note", recs[2].note, 'faces, logo "ABC"')
eq("review duplicate later wins", recs[3].decision, "candidate")
eq("review reviewed_at", recs[3].reviewedAt, "2026-10-06T11:00:00")

check("review missing column errors", not pcall(ReviewCsv.parseReview, "id,decision\r\n1,candidate\r\n"))
check("review empty errors", not pcall(ReviewCsv.parseReview, ""))

-- Round trip with a file written by Python's csv module, if provided.
local fixture = arg and arg[1]
if fixture then
	local fh = assert(io.open(fixture, "rb"))
	local data = fh:read("*a")
	fh:close()
	local r = ReviewCsv.parseReview(data)
	local expected = assert(io.open(fixture .. ".expected", "rb"))
	local i = 0
	for line in expected:lines() do
		i = i + 1
		local relpath, decision, flags, note = line:match("^(.-)\t(.-)\t(.-)\t(.*)$")
		note = note:gsub("\\n", "\n"):gsub("\\r", "\r")
		local rec = r[i] or {}
		eq("fixture relpath " .. i, rec.relpath, relpath)
		eq("fixture decision " .. i, rec.decision, decision)
		eq("fixture flags " .. i, rec.flagsText, flags)
		eq("fixture note " .. i, rec.note, note)
	end
	expected:close()
	eq("fixture count", #r, i)
end

-- Paths ----------------------------------------------------------------------

eq("join", PathMatch.join("/Users/me/Pictures/RAW_Photos/", "2019/a.ARW"), "/Users/me/Pictures/RAW_Photos/2019/a.ARW")
check("join rejects ..", PathMatch.join("/r", "a/../../etc") == nil)
check("join rejects absolute", PathMatch.join("/r", "/etc/passwd") == nil)
local d, n = PathMatch.split("/a/b/c.ARW")
eq("split dir", d, "/a/b")
eq("split name", n, "c.ARW")
eq("stemKey", PathMatch.stemKey("DSC0001.ARW"), "dsc0001")
eq("stemKey jpg pairs raw", PathMatch.stemKey("DSC0001.jpg"), PathMatch.stemKey("dsc0001.ARW"))
eq("stemKey multi dot", PathMatch.stemKey("a.b.JPG"), "a.b")
eq("stemKey no ext", PathMatch.stemKey("README"), "readme")
eq("year from path", PathMatch.yearFromReviewPath("/Users/me/out/2019/review.csv"), "2019")
eq("year none", PathMatch.yearFromReviewPath("/Users/me/out/review.csv"), nil)

print(string.format("%d/%d checks passed", total - failures, total))
os.exit(failures == 0 and 0 or 1)
