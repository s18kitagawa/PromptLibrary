--[[
Library > Plug-in Extras > Import Screening Results (review.csv)...

Reads <out_dir>/<YYYY>/review.csv, finds each file in the catalog and
  * adds it to  <Collection set> / <YYYY> / candidate | review | reject
  * stores decision, flags and note as plug-in metadata (never exported).
Files that cannot be found are listed in lightroom_unmatched.txt next to review.csv.
]]

local LrApplication = import "LrApplication"
local LrBinding = import "LrBinding"
local LrDialogs = import "LrDialogs"
local LrFileUtils = import "LrFileUtils"
local LrFunctionContext = import "LrFunctionContext"
local LrPathUtils = import "LrPathUtils"
local LrPrefs = import "LrPrefs"
local LrProgressScope = import "LrProgressScope"
local LrTasks = import "LrTasks"
local LrView = import "LrView"

local ReviewCsv = require "ReviewCsv"
local PathMatch = require "PathMatch"

local UNMATCHED_NAME = "lightroom_unmatched.txt"
local DEFAULT_SET_NAME = "Stock Screening"

local prefs = LrPrefs.prefsForPlugin()

-------------------------------------------------------------------------------
-- Dialog

local function chooseFile(props)
	local result = LrDialogs.runOpenPanel {
		title = LOC "$$$/StockScreening/ChooseCsv=Choose review.csv",
		canChooseFiles = true,
		canChooseDirectories = false,
		allowsMultipleSelection = false,
		fileTypes = { "csv" },
		initialDirectory = props.reviewCsv ~= "" and LrPathUtils.parent(props.reviewCsv) or nil,
	}
	if result and result[1] then
		props.reviewCsv = result[1]
		local year = PathMatch.yearFromReviewPath(result[1])
		if year then props.year = year end
	end
end

local function chooseFolder(props)
	local result = LrDialogs.runOpenPanel {
		title = LOC "$$$/StockScreening/ChooseRoot=Choose the photo archive folder (photos_root)",
		canChooseFiles = false,
		canChooseDirectories = true,
		allowsMultipleSelection = false,
		initialDirectory = props.photosRoot ~= "" and props.photosRoot or nil,
	}
	if result and result[1] then
		props.photosRoot = result[1]
	end
end

local function showDialog(context)
	local f = LrView.osFactory()
	local props = LrBinding.makePropertyTable(context)
	props.reviewCsv = prefs.reviewCsv or ""
	props.photosRoot = prefs.photosRoot or ""
	props.year = PathMatch.yearFromReviewPath(props.reviewCsv) or ""
	props.setName = prefs.setName or DEFAULT_SET_NAME
	props.doCandidate = prefs.doCandidate ~= false
	props.doReview = prefs.doReview ~= false
	props.doReject = prefs.doReject == true
	props.replace = prefs.replace ~= false
	props.writeMetadata = prefs.writeMetadata ~= false

	local labelWidth = LrView.share "label_width"
	local contents = f:column {
		bind_to_object = props,
		spacing = f:control_spacing(),

		f:row {
			f:static_text { title = LOC "$$$/StockScreening/ReviewCsv=review.csv:", alignment = "right", width = labelWidth },
			f:edit_field { value = LrView.bind "reviewCsv", width_in_chars = 40 },
			f:push_button { title = LOC "$$$/StockScreening/Browse=Browse...", action = function() chooseFile(props) end },
		},
		f:row {
			f:static_text { title = LOC "$$$/StockScreening/PhotosRoot=Photo archive:", alignment = "right", width = labelWidth },
			f:edit_field { value = LrView.bind "photosRoot", width_in_chars = 40 },
			f:push_button { title = LOC "$$$/StockScreening/Browse=Browse...", action = function() chooseFolder(props) end },
		},
		f:row {
			f:static_text { title = "", width = labelWidth },
			f:static_text {
				title = LOC "$$$/StockScreening/PhotosRootHint=The folder used as photos_root for screening, as this Mac sees it.",
				size = "small",
			},
		},
		f:row {
			f:static_text { title = LOC "$$$/StockScreening/Year=Year:", alignment = "right", width = labelWidth },
			f:edit_field { value = LrView.bind "year", width_in_chars = 6 },
		},
		f:row {
			f:static_text { title = LOC "$$$/StockScreening/SetName=Collection set:", alignment = "right", width = labelWidth },
			f:edit_field { value = LrView.bind "setName", width_in_chars = 20 },
		},
		f:separator { fill_horizontal = 1 },
		f:row {
			f:static_text { title = LOC "$$$/StockScreening/Decisions=Collections:", alignment = "right", width = labelWidth },
			f:checkbox { title = "candidate", value = LrView.bind "doCandidate" },
			f:checkbox { title = "review", value = LrView.bind "doReview" },
			f:checkbox { title = "reject", value = LrView.bind "doReject" },
		},
		f:row {
			f:static_text { title = "", width = labelWidth },
			f:checkbox {
				title = LOC "$$$/StockScreening/Replace=Replace collection contents (reflect changed decisions)",
				value = LrView.bind "replace",
			},
		},
		f:row {
			f:static_text { title = "", width = labelWidth },
			f:checkbox {
				title = LOC "$$$/StockScreening/WriteMetadata=Store decision, flags and note as plug-in metadata",
				value = LrView.bind "writeMetadata",
			},
		},
	}

	local result = LrDialogs.presentModalDialog {
		title = LOC "$$$/StockScreening/DialogTitle=Import Screening Results",
		contents = contents,
		actionVerb = LOC "$$$/StockScreening/Import=Import",
	}
	if result ~= "ok" then return nil end

	prefs.reviewCsv = props.reviewCsv
	prefs.photosRoot = props.photosRoot
	prefs.setName = props.setName
	prefs.doCandidate = props.doCandidate
	prefs.doReview = props.doReview
	prefs.doReject = props.doReject
	prefs.replace = props.replace
	prefs.writeMetadata = props.writeMetadata

	return {
		reviewCsv = props.reviewCsv,
		photosRoot = (props.photosRoot:gsub("/+$", "")),
		year = (props.year:gsub("^%s+", ""):gsub("%s+$", "")),
		setName = (props.setName:gsub("^%s+", ""):gsub("%s+$", "")),
		decisions = {
			candidate = props.doCandidate,
			review = props.doReview,
			reject = props.doReject,
		},
		replace = props.replace,
		writeMetadata = props.writeMetadata,
	}
end

local function validate(opts)
	if opts.reviewCsv == "" or LrFileUtils.exists(opts.reviewCsv) ~= "file" then
		return LOC("$$$/StockScreening/ErrCsv=review.csv not found: ^1", opts.reviewCsv)
	end
	if opts.photosRoot == "" or LrFileUtils.exists(opts.photosRoot) ~= "directory" then
		return LOC("$$$/StockScreening/ErrRoot=Photo archive folder not found: ^1", opts.photosRoot)
	end
	if opts.year == "" then
		return LOC "$$$/StockScreening/ErrYear=Enter the year (used as the collection set name)."
	end
	if opts.setName == "" then
		return LOC "$$$/StockScreening/ErrSet=Enter a collection set name."
	end
	if not (opts.decisions.candidate or opts.decisions.review or opts.decisions.reject) then
		return LOC "$$$/StockScreening/ErrNone=Select at least one collection."
	end
	return nil
end

-------------------------------------------------------------------------------
-- Matching

--[[
Find the catalog photo for one relpath:
  1. exact path (case-insensitive)
  2. another file of the same frame in the same folder (same name, other extension), e.g.
     the RAW when the screening kept the JPEG of a RAW+JPEG pair, or vice versa
     (Lightroom may treat the JPEG as a sidecar that is not a photo of its own).
]]
local function makeMatcher(catalog, photosRoot)
	local folderIndex = {} -- dir -> { stemKey -> photo } or false

	local function indexFolder(dir)
		local cached = folderIndex[dir]
		if cached ~= nil then return cached end
		local folder = catalog:getFolderByPath(dir)
		local map = false
		if folder then
			map = {}
			for _, photo in ipairs(folder:getPhotos(false)) do
				if not photo:getRawMetadata("isVirtualCopy") then
					local name = LrPathUtils.leafName(photo:getRawMetadata("path"))
					local key = PathMatch.stemKey(name)
					if map[key] == nil then map[key] = photo end
				end
			end
		end
		folderIndex[dir] = map
		return map
	end

	return function(relpath)
		local path, err = PathMatch.join(photosRoot, relpath)
		if not path then return nil, err end
		local photo = catalog:findPhotoByPath(path, false)
		if photo then return photo, "exact" end
		local dir, name = PathMatch.split(path)
		local map = indexFolder(dir)
		if map then
			photo = map[PathMatch.stemKey(name)]
			if photo then return photo, "sibling" end
			return nil, "not in catalog (folder is imported)"
		end
		return nil, "folder not in catalog"
	end
end

-------------------------------------------------------------------------------
-- Main

local function writeUnmatched(reviewCsv, unmatched)
	local path = LrPathUtils.child(LrPathUtils.parent(reviewCsv), UNMATCHED_NAME)
	if #unmatched == 0 then
		if LrFileUtils.exists(path) == "file" then LrFileUtils.delete(path) end
		return nil
	end
	local fh = io.open(path, "w")
	if not fh then return nil end
	fh:write("# Files from review.csv not found in the Lightroom catalog\n")
	fh:write("# decision\trelpath\treason\n")
	for _, u in ipairs(unmatched) do
		fh:write(u.decision .. "\t" .. u.relpath .. "\t" .. u.reason .. "\n")
	end
	fh:close()
	return path
end

local function run(context)
	local opts = showDialog(context)
	if not opts then return end
	local errMsg = validate(opts)
	if errMsg then
		LrDialogs.message(LOC "$$$/StockScreening/ErrTitle=Stock Screening", errMsg, "critical")
		return
	end

	-- The year is not re-read when the path is typed by hand; a stale year would replace another year's collections.
	local csvYear = PathMatch.yearFromReviewPath(opts.reviewCsv)
	if csvYear and csvYear ~= opts.year then
		local answer = LrDialogs.confirm(
			LOC("$$$/StockScreening/YearMismatch=Year ^1 does not match the review.csv folder (^2).", opts.year, csvYear),
			LOC("$$$/StockScreening/YearMismatchInfo=Results will go into ^1 / ^2.", opts.setName, opts.year),
			LOC "$$$/StockScreening/ImportAnyway=Import Anyway")
		if answer ~= "ok" then return end
	end

	local text = LrFileUtils.readFile(opts.reviewCsv)
	local ok, records, warnings = pcall(ReviewCsv.parseReview, text or "")
	if not ok then
		LrDialogs.message(LOC "$$$/StockScreening/ErrTitle=Stock Screening", tostring(records), "critical")
		return
	end

	local catalog = LrApplication.activeCatalog()
	local progress = LrProgressScope {
		title = LOC "$$$/StockScreening/Progress=Matching review.csv to the catalog",
		functionContext = context,
	}

	-- 1. Match (read-only).
	local match = makeMatcher(catalog, opts.photosRoot)
	local matched, unmatched = {}, {}
	local counts = { exact = 0, sibling = 0 }
	for i, rec in ipairs(records) do
		if progress:isCanceled() then return end
		progress:setPortionComplete(i - 1, #records)
		local photo, how = match(rec.relpath)
		if photo then
			matched[#matched + 1] = { photo = photo, rec = rec }
			counts[how] = counts[how] + 1
		else
			unmatched[#unmatched + 1] = { relpath = rec.relpath, decision = rec.decision, reason = how }
		end
	end
	progress:setPortionComplete(1, 1)

	-- 2. Collections and metadata (one undoable step).
	local perDecision = { candidate = {}, review = {}, reject = {} }
	for _, m in ipairs(matched) do
		local list = perDecision[m.rec.decision]
		list[#list + 1] = m.photo
	end

	local collections = {}
	local status = catalog:withWriteAccessDo(LOC "$$$/StockScreening/Undo=Import Screening Results", function()
		local topSet = catalog:createCollectionSet(opts.setName, nil, true)
		local yearSet = catalog:createCollectionSet(opts.year, topSet, true)
		for _, decision in ipairs(ReviewCsv.DECISIONS) do
			if opts.decisions[decision] then
				local coll = catalog:createCollection(decision, yearSet, true)
				if opts.replace then coll:removeAllPhotos() end
				if #perDecision[decision] > 0 then coll:addPhotos(perDecision[decision]) end
				collections[#collections + 1] = { decision = decision, collection = coll }
			end
		end
		if opts.writeMetadata then
			for _, m in ipairs(matched) do
				local function set(field, value)
					m.photo:setPropertyForPlugin(_PLUGIN, field, (value ~= nil and value ~= "") and value or nil)
				end
				set("decision", m.rec.decision)
				set("flags", m.rec.flagsText)
				set("note", m.rec.note)
				set("year", opts.year)
				set("reviewedAt", m.rec.reviewedAt)
			end
		end
	end, { timeout = 60 })

	progress:done()

	if status == "aborted" then
		LrDialogs.message(LOC "$$$/StockScreening/ErrTitle=Stock Screening",
			LOC "$$$/StockScreening/ErrAborted=The catalog is busy (another task is writing to it). Nothing was imported; try again later.",
			"critical")
		return
	end

	if collections[1] then
		catalog:setActiveSources { collections[1].collection }
	end

	-- 3. Report.
	local unmatchedPath = writeUnmatched(opts.reviewCsv, unmatched)
	local lines = {}
	lines[#lines + 1] = LOC("$$$/StockScreening/SumRows=review.csv: ^1 files", tostring(#records))
	for _, c in ipairs(collections) do
		lines[#lines + 1] = string.format("  %s / %s / %s: %d",
			opts.setName, opts.year, c.decision, #perDecision[c.decision])
	end
	lines[#lines + 1] = LOC("$$$/StockScreening/SumMatched=Matched: ^1 (by path ^2, same name other extension ^3)",
		tostring(#matched), tostring(counts.exact), tostring(counts.sibling))
	if unmatchedPath then
		lines[#lines + 1] = LOC("$$$/StockScreening/SumUnmatched=Not found in catalog: ^1 - see ^2",
			tostring(#unmatched), unmatchedPath)
	elseif #unmatched > 0 then
		-- The list file could not be written (e.g. read-only folder): show the first entries here.
		lines[#lines + 1] = LOC("$$$/StockScreening/SumUnmatchedNoFile=Not found in catalog: ^1 (could not write ^2)",
			tostring(#unmatched), UNMATCHED_NAME)
		for i = 1, math.min(#unmatched, 10) do
			lines[#lines + 1] = "  " .. unmatched[i].relpath .. " - " .. unmatched[i].reason
		end
	end
	if #warnings > 0 then
		lines[#lines + 1] = LOC("$$$/StockScreening/SumWarnings=Skipped rows: ^1 (first: ^2)", tostring(#warnings), warnings[1])
	end
	LrDialogs.message(LOC "$$$/StockScreening/DoneTitle=Screening results imported",
		table.concat(lines, "\n"), #unmatched > 0 and "warning" or "info")
end

LrTasks.startAsyncTask(function()
	LrFunctionContext.callWithContext("StockScreening.ImportReview", run)
end)
