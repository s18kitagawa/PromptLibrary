--[[
Path helpers for matching review.csv rows to catalog photos.

Pure Lua 5.1 (no Lightroom APIs) so it can be unit-tested outside Lightroom.
review.csv stores POSIX paths relative to the photo archive root (photos_root).
]]

local PathMatch = {}

-- Join the archive root (absolute, as Lightroom sees it) and a relpath from review.csv.
-- Returns nil, message for relpaths that would escape the root.
function PathMatch.join(root, relpath)
	if relpath:sub(1, 1) == "/" then
		return nil, "relpath is absolute: " .. relpath
	end
	for part in relpath:gmatch("[^/]+") do
		if part == ".." then
			return nil, "relpath contains '..': " .. relpath
		end
	end
	root = root:gsub("/+$", "")
	return root .. "/" .. relpath
end

-- "/a/b/c.ARW" -> "/a/b", "c.ARW"
function PathMatch.split(path)
	local dir, name = path:match("^(.*)/([^/]*)$")
	if not dir then return "", path end
	return dir, name
end

-- Key used to find another file of the same frame in the same folder:
-- file name without its last extension, ASCII-lowercased. "DSC0001.ARW" -> "dsc0001"
function PathMatch.stemKey(name)
	local stem = name:match("^(.+)%.[^.]*$") or name
	return stem:lower()
end

-- Capture year from the folder that holds review.csv: ".../out/2019/review.csv" -> "2019"
function PathMatch.yearFromReviewPath(path)
	local dir = PathMatch.split(path)
	local _, leaf = PathMatch.split(dir)
	if leaf:match("^%d%d%d%d$") then return leaf end
	return nil
end

return PathMatch
