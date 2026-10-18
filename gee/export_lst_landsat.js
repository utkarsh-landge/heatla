/**
 * HEATLA - peak summer land-surface temperature by census tract.
 *
 * Landsat 8/9 Collection 2 Level 2 surface temperature (band ST_B10),
 * cloud-masked, June-September 2021-2025, reduced to the per-pixel MAXIMUM
 * (peak heat, not average heat - the cooling-centre question is about the
 * worst days), then averaged within each tract.
 *
 * Run in the Earth Engine Code Editor, then put the exported CSV at
 * data/raw/gee_lst_landsat.csv.
 */
var tracts = ee.FeatureCollection('TIGER/2020/TRACT')
    .filter(ee.Filter.eq('STATEFP', '06'))
    .filter(ee.Filter.eq('COUNTYFP', '037'));

function maskL2sr(img) {
  // QA_PIXEL bits: 1 dilated cloud, 2 cirrus, 3 cloud, 4 cloud shadow.
  var qa = img.select('QA_PIXEL');
  var clear = qa.bitwiseAnd(1 << 1).eq(0)
      .and(qa.bitwiseAnd(1 << 2).eq(0))
      .and(qa.bitwiseAnd(1 << 3).eq(0))
      .and(qa.bitwiseAnd(1 << 4).eq(0));
  // ST_B10 scaling to kelvin, then to fahrenheit.
  var k = img.select('ST_B10').multiply(0.00341802).add(149.0);
  var f = k.subtract(273.15).multiply(9 / 5).add(32).rename('lst_f');
  return f.updateMask(clear).copyProperties(img, ['system:time_start']);
}

var col = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
    .merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2'))
    .filterBounds(tracts)
    .filterDate('2021-01-01', '2026-01-01')
    .filter(ee.Filter.calendarRange(6, 9, 'month'))
    .filter(ee.Filter.lt('CLOUD_COVER', 40))
    .map(maskL2sr);

var peak = col.max();

var out = peak.reduceRegions({
  collection: tracts,
  reducer: ee.Reducer.mean(),
  scale: 30,
  tileScale: 4
}).map(function (f) {
  return ee.Feature(null, {GEOID: f.get('GEOID'), lst_f: f.get('mean')});
});

Export.table.toDrive({
  collection: out,
  description: 'heatla_gee_lst_landsat',
  fileNamePrefix: 'gee_lst_landsat',
  fileFormat: 'CSV',
  selectors: ['GEOID', 'lst_f']
});
