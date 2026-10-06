--[[
Stock Screening - Lightroom Classic plug-in

Imports the visual-review decisions of the stock-screening tool (<out_dir>/<YYYY>/review.csv)
into collections, so the candidates can be published with Lightroom's Adobe Stock service.
]]

return {
	LrSdkVersion = 10.0,
	LrSdkMinimumVersion = 6.0,

	LrToolkitIdentifier = "io.github.stockscreening.lightroom",
	LrPluginName = LOC "$$$/StockScreening/PluginName=Stock Screening",

	-- Library > Plug-in Extras and File > Plug-in Extras
	LrLibraryMenuItems = {
		{
			title = LOC "$$$/StockScreening/MenuImport=Import Screening Results (review.csv)...",
			file = "ImportReview.lua",
		},
	},
	LrExportMenuItems = {
		{
			title = LOC "$$$/StockScreening/MenuImport=Import Screening Results (review.csv)...",
			file = "ImportReview.lua",
		},
	},

	-- Decision / flags / note are stored as plug-in metadata: searchable and usable in smart
	-- collections, but never written to exported or published files (unlike keywords/caption).
	LrMetadataProvider = "MetadataDefinition.lua",
	LrMetadataTagsetFactory = "Tagset.lua",

	VERSION = { major = 0, minor = 2, revision = 0 },
}
