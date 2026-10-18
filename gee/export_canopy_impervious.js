/**
 * HEATLA - tree canopy and impervious surface by census tract.
 *
 * NLCD 2021 impervious surface and the USFS/NLCD tree canopy layer, both at
 * 30 m, averaged within each tract.
 *
 * Outputs -> data/raw/gee_canopy.csv, data/raw/gee_impervious.csv
 */
var tracts = ee.FeatureCollection('TIGER/2020/TRACT')
    .filter(ee.Filter.eq('STATEFP', '06'))
    .filter(ee.Filter.eq('COUNTYFP', '037'));

var nlcd = ee.ImageCollection('USGS/NLCD_RELEASES/2021_REL/NLCD')
    .filter(ee.Filter.eq('system:index', '2021')).first();
var imperv = nlcd.select('impervious').rename('pct_impervious');

var canopy = ee.ImageCollection('USFS/GTAC/TreeCanopyCover/v2021-4')
    .filterDate('2021-01-01', '2022-01-01').first()
    .select('cover').rename('pct_canopy');

function exportMean(img, band, name) {
  var out = img.reduceRegions({
    collection: tracts, reducer: ee.Reducer.mean(), scale: 30, tileScale: 4
  }).map(function (f) {
    var o = {GEOID: f.get('GEOID')};
    o[band] = f.get('mean');
    return ee.Feature(null, o);
  });
  Export.table.toDrive({
    collection: out, description: 'heatla_' + name, fileNamePrefix: name,
    fileFormat: 'CSV', selectors: ['GEOID', band]
  });
}

exportMean(imperv, 'pct_impervious', 'gee_impervious');
exportMean(canopy, 'pct_canopy', 'gee_canopy');
