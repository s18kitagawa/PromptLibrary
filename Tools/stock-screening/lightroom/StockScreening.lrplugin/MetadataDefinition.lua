--[[
Plug-in metadata fields (shown in the Metadata panel under "Stock Screening" or
"All Plug-in Metadata"). Read-only in the UI; written by ImportReview.lua.
Bump schemaVersion if fields change.
]]

local function field(id, title)
	return {
		id = id,
		title = title,
		dataType = "string",
		readOnly = true,
		searchable = true,
		browsable = true,
	}
end

return {
	metadataFieldsForPhotos = {
		field("decision", LOC "$$$/StockScreening/Field/Decision=Decision"),
		field("flags", LOC "$$$/StockScreening/Field/Flags=Flags"),
		field("note", LOC "$$$/StockScreening/Field/Note=Note"),
		field("year", LOC "$$$/StockScreening/Field/Year=Screening Year"),
		field("reviewedAt", LOC "$$$/StockScreening/Field/ReviewedAt=Reviewed At"),
	},
	schemaVersion = 1,
}
