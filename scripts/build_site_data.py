"""Step 6a - export real pipeline outputs as static site data (no synthetic values).

Writes into site/data/:
  zips.geojson   - LA ZIP polygons (geometry from the UCLA zip_ER layer) with
                   observed + out-of-fold predicted excess ER, group, key features
  centers.json   - real LA County cooling centers (lat/lon, name)
  metrics.json   - Step 4 model metrics (copied from results/)
  solutions.json - Step 5 cooling-center solutions (copied from results/)
  meta.json      - provenance, counts, honest-labeling notes

Everything here is derived from the real pipeline outputs. Nothing is generated.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys
import urllib.parse
import urllib.request

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from heatla import arcgis  # noqa: E402

SITE = pathlib.Path("site/data")
RES = pathlib.Path("results")


def fetch_zip_polygons() -> dict:
    """One generalized polygon per LA ZIP from the target layer (outSR 4326)."""
    base = arcgis.UCLA_SERVICES
    url = f"{base}/zip_ER/FeatureServer/0/query?" + urllib.parse.urlencode({
        "where": "cnty_nm='Los Angeles' AND categry=4 AND NumRate='Rate' AND Years='2008-2018'",
        "outFields": "zip",
        "returnGeometry": "true",
        "outSR": "4326",
        "maxAllowableOffset": "0.0007",  # generalize to keep the file small
        "f": "geojson",
    })
    return json.load(urllib.request.urlopen(url, timeout=120))


def load_projection_2030() -> dict:
    """Per-ZIP 2030 projection, pivoted wide from the long heat_factor table."""
    path = pathlib.Path("data/processed/heat_factor_2030.csv")
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    out: dict[int, dict] = {}
    for scen, sub in df.groupby("scenario"):
        tag = str(scen).replace("rcp", "rcp")  # rcp45 / rcp85
        for r in sub.itertuples():
            d = out.setdefault(int(r.zip), {})
            d[f"factor_{tag}"] = round(float(r.heat_factor), 3)
            d[f"proj_{tag}"] = round(float(r.projected_rate_2030), 2)
    return out


def main() -> None:
    SITE.mkdir(parents=True, exist_ok=True)
    grouped = pd.read_csv("data/processed/model_table_grouped.csv")
    oof = pd.read_csv("results/predictions_oof.csv")
    data = grouped.merge(oof, on="zip", suffixes=("", "_oof"))
    by_zip = {int(r.zip): r for r in data.itertuples()}
    proj2030 = load_projection_2030()

    gj = fetch_zip_polygons()
    keep = []
    for feat in gj["features"]:
        z = int(feat["properties"]["zip"])
        r = by_zip.get(z)
        if r is None:
            continue  # zip with no model row (missing coords) - omit from map
        feat["properties"] = {
            "zip": z,
            "observed_rate": round(float(r.excess_er_rate_per_10k), 2),
            "observed_number": round(float(r.excess_er_number), 1),
            "pred_poisson": round(float(r.pred_poisson), 2),
            "pred_rf": round(float(r.pred_random_forest), 2),
            "pred_gbm": round(float(r.pred_gradient_boosting), 2),
            "group": int(r.group),
            "population": int(r.ucla_population),
            "median_hh_income": None if pd.isna(r.median_hh_income) else int(r.median_hh_income),
            "pct_poverty": None if pd.isna(r.pct_poverty) else round(float(r.pct_poverty), 1),
            "ces4_percentile": None if pd.isna(r.ces4_percentile) else round(float(r.ces4_percentile), 1),
            "is_90095": int(r.is_ucla_campus_90095),
        }
        feat["properties"].update(proj2030.get(z, {}))
        keep.append(feat)
    gj["features"] = keep
    (SITE / "zips.geojson").write_text(json.dumps(gj))

    centers = json.load(open("data/raw/cooling_centers_lacounty.json"))
    clist = [
        {"name": f["attributes"].get("Site_Name"),
         "city": (f["attributes"].get("City") or "").strip(),
         "lat": f["geometry"]["y"], "lon": f["geometry"]["x"]}
        for f in centers["features"] if f.get("geometry", {}).get("x") is not None
    ]
    (SITE / "centers.json").write_text(json.dumps(clist))

    (SITE / "metrics.json").write_text((RES / "metrics.json").read_text())
    (SITE / "solutions.json").write_text((RES / "coolingcenter_solutions.json").read_text())

    # Statewide validation, ZIP->tract downscale, and 2030 outlook.
    # Results contain NaN (valid in Python, invalid JSON -> browsers reject). Scrub NaN/Inf to null.
    def scrub(o):
        if isinstance(o, float) and not math.isfinite(o):
            return None
        if isinstance(o, dict):
            return {k: scrub(v) for k, v in o.items()}
        if isinstance(o, list):
            return [scrub(v) for v in o]
        return o
    extra = 0
    for name in ("metrics_ca.json", "downscale_validation.json", "projection_2030.json"):
        src = RES / name
        if src.exists():
            (SITE / name).write_text(json.dumps(scrub(json.loads(src.read_text()))))
            extra += 1

    (SITE / "meta.json").write_text(json.dumps({
        "title": "HEATLA \u2014 LA County heat-related excess ER visits",
        "n_zips_mapped": len(keep),
        "n_zips_projected_2030": len(proj2030),
        "target": 'UCLA Heat Maps estimated excess ER visits per 10,000 residents, CalHeatScore level 4 layer, total over May-October 2008-2018',
        "data_years": {"target": "2008-2018", "CES": "4.0 (data from 2013-2019, published 2021)",
                       "ACS": "2022 5-year",
                       "cooling_centers": "LA County official, 2022",
                       "climate": "Cal-Adapt exheat_year_ens32avg (LOCA 32-model), 2026-2035 vs 2008-2018"},
        "headline": "Out-of-region skill within heat level 4 (LA hold-out, Poisson): Spearman 0.674.",
        "caveats": [
            "The target is UCLA's model-based estimate, not a direct count: observed heat-related ER visits minus the visits a Bayesian spatial model expects at typical temperatures.",
            "The level-4 value is a total over May-October 2008-2018 and covers every heat day up to and including level 4, not only the most extreme days.",
            "ZIP-level only; no daily or individual records.",
            "Small sample (~287 ZIPs); mismatched data years across sources.",
            "Missing model inputs are filled with the training-fold median before fitting.",
            "LA predictions are shown in two versions: out-of-fold (trained on other LA ZIPs) and holdout (trained on the rest of California).",
            "Pooled all-CHS hold-out numbers mostly reflect the gap between heat levels; the within-level measure is CHS-4-only Poisson Spearman 0.674.",
            "The ZIP-to-tract downscale is checked only by a pseudo-ZIP recovery test; there is no tract-level health data to validate against.",
            "The 2030 layer is a proportional heat-exposure scaling scenario, not a model prediction and not part of model evaluation.",
            "Cooling-center selection picks among the 153 existing centers and measures straight-line coverage of ZIP centroids, not actual access or health benefit.",
            "ZIP 90095 (UCLA) may have mis-attributed ER patients; flagged.",
            "Prototype study, not an operational tool.",
        ],
    }, indent=2))

    print(f"site data written: {len(keep)} zip polygons, {len(clist)} centers, "
          f"{len(proj2030)} with 2030 projection, {extra} extra result files")


if __name__ == "__main__":
    main()
