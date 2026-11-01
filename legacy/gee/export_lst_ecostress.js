/**
 * HEATLA - ECOSTRESS land-surface temperature by census tract (optional
 * upgrade path).
 *
 * Landsat gives one daytime overpass around 10:30 local, which misses the
 * night-time heat that matters most for health: people die in homes that do
 * not cool down overnight. ECOSTRESS flies on the ISS, so its overpasses
 * drift across the diurnal cycle and include night, at ~70 m.
 *
 * This export produces two columns: the summer daytime max and the summer
 * night-time mean. Set lst_source: ecostress in config.yaml to use it; the
 * default stays Landsat until the advisor signs off.
 *
 * Output -> data/raw/gee_lst_ecostress.csv
 */
var tracts = ee.FeatureCollection('TIGER/2020/TRACT')
    .filter(ee.Filter.eq('STATEFP', '06'))
    .filter(ee.Filter.eq('COUNTYFP', '037'));

// ECO2LSTE / ECO_L2T_LSTE. Asset id depends on what is current in the EE
// catalogue; check the catalogue entry before running.
var eco = ee.ImageCollection('NASA/ECOSTRESS/L2T_LSTE/V2')
    .filterBounds(tracts)
    .filterDate('2021-01-01', '2026-01-01')
    .filter(ee.Filter.calendarRange(6, 9, 'month'));

function toF(img) {
  var qc = img.select('QC');
  var good = qc.bitwiseAnd(3).eq(0);          // mandatory QA: best quality
  var f = img.select('LST').multiply(0.02)     // kelvin
      .subtract(273.15).multiply(9 / 5).add(32).rename('lst_f');
  return f.updateMask(good).copyProperties(img, ['system:time_start']);
}

var hour = function (img) {
  return ee.Date(img.get('system:time_start')).get('hour');
};

var day = eco.filter(ee.Filter.calendarRange(10, 17, 'hour')).map(toF).max()
    .rename('lst_f');
var night = eco.filter(ee.Filter.calendarRange(22, 5, 'hour')).map(toF).mean()
    .rename('lst_night_f');

var out = day.addBands(night).reduceRegions({
  collection: tracts,
  reducer: ee.Reducer.mean(),
  scale: 70,
  tileScale: 4
}).map(function (f) {
  return ee.Feature(null, {
    GEOID: f.get('GEOID'),
    lst_f: f.get('lst_f'),
    lst_night_f: f.get('lst_night_f')
  });
});

Export.table.toDrive({
  collection: out,
  description: 'heatla_gee_lst_ecostress',
  fileNamePrefix: 'gee_lst_ecostress',
  fileFormat: 'CSV',
  selectors: ['GEOID', 'lst_f', 'lst_night_f']
});
