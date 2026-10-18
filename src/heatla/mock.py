"""Synthetic LA-shaped county.

The point of this module is to let Parts A, B and C run end-to-end before any
real download lands, and to give the unit tests something deterministic to
chew on. Nothing here is ever reported as a finding: run_all stamps every
output with the data mode, and the report says plainly when it is mock.

The fields are generated with spatial structure (smoothed noise), because an
optimiser that only ever sees spatially independent noise would look better
than it really is: with no clustering, every candidate site covers a random
draw of tracts and greedy has nothing to exploit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon, Point

from .config import Config, COUNTY_GEOID_PREFIX, CRS_WORK, CRS_GEO


def _smooth_field(rng: np.random.Generator, nx: int, ny: int, scale: int) -> np.ndarray:
    """A cheap Gaussian random field: white noise passed through a box blur."""
    f = rng.normal(size=(ny, nx))
    for _ in range(scale):
        f = (f
             + np.roll(f, 1, 0) + np.roll(f, -1, 0)
             + np.roll(f, 1, 1) + np.roll(f, -1, 1)) / 5.0
    f -= f.mean()
    sd = f.std()
    return f / sd if sd > 0 else f


def _la_mask(xx: np.ndarray, yy: np.ndarray) -> np.ndarray:
    """A blobby county outline, vaguely LA-shaped: a wide coastal basin plus an
    inland valley lobe to the north, with the ocean cut out of the south-west."""
    basin = ((xx - 0.45) / 0.42) ** 2 + ((yy - 0.38) / 0.26) ** 2 < 1.0
    valley = ((xx - 0.62) / 0.34) ** 2 + ((yy - 0.74) / 0.22) ** 2 < 1.0
    ocean = (yy < 0.22 - 0.25 * xx)
    return (basin | valley) & ~ocean


def build_mock(cfg: Config) -> dict[str, object]:
    """Return mock tracts (GeoDataFrame), centres (GeoDataFrame) and ZIP-level
    ER rates (DataFrame), all in real-world coordinates near Los Angeles."""
    rng = np.random.default_rng(cfg.seed)
    n_target = cfg.mock_n_tracts

    # Grid fine enough that the masked cell count lands near n_target.
    nx = ny = int(np.ceil(np.sqrt(n_target / 0.52)))
    gx, gy = np.meshgrid((np.arange(nx) + 0.5) / nx, (np.arange(ny) + 0.5) / ny)
    mask = _la_mask(gx, gy)
    idx = np.argwhere(mask)
    if len(idx) > n_target:                      # trim deterministically
        keep = rng.choice(len(idx), n_target, replace=False)
        keep.sort()
        idx = idx[keep]
    n = len(idx)

    # Real-world extent: LA County spans roughly 118.95W-117.65W, 33.70N-34.82N.
    lon0, lon1, lat0, lat1 = -118.95, -117.65, 33.70, 34.82
    cw, ch = (lon1 - lon0) / nx, (lat1 - lat0) / ny

    fields = {name: _smooth_field(rng, nx, ny, s) for name, s in
              [("heat", 40), ("wealth", 30), ("age", 25), ("green", 35),
               ("dense", 20), ("pollute", 30)]}
    at = lambda name: fields[name][idx[:, 0], idx[:, 1]]  # noqa: E731

    heat, wealth, age, green, dense, pollute = (at(k) for k in
                                                ("heat", "wealth", "age", "green",
                                                 "dense", "pollute"))
    # Inland and low-elevation-valley tracts run hotter; the coast stays cool.
    coast_dist = (idx[:, 1] / nx) * 0.7 + (idx[:, 0] / ny) * 0.5
    heat = 0.65 * heat + 1.35 * (coast_dist - coast_dist.mean()) / coast_dist.std()

    geoms, lons, lats = [], [], []
    for r, c in idx:
        x0, y0 = lon0 + c * cw, lat0 + r * ch
        geoms.append(Polygon([(x0, y0), (x0 + cw, y0), (x0 + cw, y0 + ch), (x0, y0 + ch)]))
        lons.append(x0 + cw / 2)
        lats.append(y0 + ch / 2)

    def clip(v, lo, hi):
        return np.clip(v, lo, hi)

    # Tracts are drawn to hold ~4,000 people, so population varies modestly.
    pop = clip(np.round(4000 + 900 * dense + rng.normal(0, 450, n)), 400, 12000)

    # Wealth drives poverty and income; it is negatively tied to heat, which is
    # the association Part B is meant to recover.
    pct_poverty = clip(16 - 7.0 * wealth + 2.2 * heat + rng.normal(0, 2.6, n), 1.0, 62.0)
    median_income = clip(np.round(78000 + 26000 * wealth - 7000 * heat
                                  + rng.normal(0, 9000, n), -2), 18000, 250000)
    pct_age65p = clip(14.5 + 4.2 * age - 0.9 * dense + rng.normal(0, 2.0, n), 2.0, 46.0)
    pct_under5 = clip(5.8 - 1.4 * age + 0.9 * dense + 0.5 * pct_poverty / 10
                      + rng.normal(0, 1.1, n), 0.3, 16.0)
    pct_under18 = clip(21.0 - 3.6 * age + 2.1 * dense + 1.4 * pct_poverty / 10
                       + rng.normal(0, 2.4, n), 2.0, 48.0)

    pct_canopy = clip(17 + 7.5 * green + 4.0 * wealth - 3.2 * heat
                      + rng.normal(0, 3.0, n), 0.5, 62.0)
    pct_impervious = clip(55 + 9 * dense - 0.55 * pct_canopy + 4 * heat
                          + rng.normal(0, 5.0, n), 5.0, 98.0)
    lst_f = clip(96 + 7.2 * heat - 0.16 * pct_canopy + 0.07 * pct_impervious
                 + rng.normal(0, 1.7, n), 74.0, 128.0)

    # Race/ethnicity shares: correlated with poverty, then normalised to 100.
    hisp = clip(44 + 15 * (pct_poverty - 16) / 10 + rng.normal(0, 11, n), 2, 95)
    black = clip(8 + 5 * (pct_poverty - 16) / 10 + rng.normal(0, 6, n), 0.2, 70)
    asian = clip(15 + 6 * wealth + rng.normal(0, 8, n), 0.3, 75)
    other = clip(4 + rng.normal(0, 1.6, n), 0.2, 14)
    white = clip(100 - hisp - black - asian - other, 1.0, None)
    tot = hisp + black + asian + other + white
    hisp, black, asian, other, white = (100 * v / tot for v in (hisp, black, asian, other, white))

    ces_pollution = clip(45 + 11 * pollute + 8 * dense + 5 * heat
                         + rng.normal(0, 7, n), 1, 99)
    ces_score = clip(30 + 7 * pollute + 6.5 * (pct_poverty - 16) / 4
                     + 3.5 * heat + rng.normal(0, 4.5, n), 1, 99)
    # CDC SVI is a 0-1 percentile; driven by poverty, minority share, crowding.
    svi_raw = (pct_poverty / 40 + (100 - white) / 150 + (1 - wealth) / 6
               + rng.normal(0, 0.09, n))
    svi = pd.Series(svi_raw).rank(pct=True).to_numpy()

    geoid = [f"{COUNTY_GEOID_PREFIX}{i:06d}" for i in range(1, n + 1)]

    tracts = gpd.GeoDataFrame(
        {
            "GEOID": geoid,
            "pop": pop.astype(int),
            "pct_age65p": pct_age65p.round(2),
            "pct_under5": pct_under5.round(2),
            "pct_under18": pct_under18.round(2),
            "pct_poverty": pct_poverty.round(2),
            "median_income": median_income.astype(int),
            "pct_hispanic": hisp.round(2),
            "pct_black": black.round(2),
            "pct_asian": asian.round(2),
            "pct_white_nh": white.round(2),
            "pct_other_race": other.round(2),
            "lst_f": lst_f.round(2),
            "pct_canopy": pct_canopy.round(2),
            "pct_impervious": pct_impervious.round(2),
            "ces_score": ces_score.round(2),
            "ces_pollution_pctl": ces_pollution.round(2),
            "svi": svi.round(4),
            "INTPTLON": np.round(lons, 6),
            "INTPTLAT": np.round(lats, 6),
        },
        geometry=geoms, crs=CRS_GEO,
    )

    # --- ZIP-level heat ER visits, so the crosswalk code has something to do --
    # Build ~300 pseudo-ZIPs by clustering tracts, then emit a ZIP-level rate.
    n_zip = 300
    zcent = rng.choice(n, n_zip, replace=False)
    pts = np.c_[tracts["INTPTLON"], tracts["INTPTLAT"]]
    d = ((pts[:, None, :] - pts[zcent][None, :, :]) ** 2).sum(-1)
    zip_assign = d.argmin(1)
    tracts["ZCTA_mock"] = [f"9{1000 + z:04d}" for z in zip_assign]

    # True (unobserved) tract-level risk; ER rate is its ZIP mean plus noise, so
    # the HVI validation correlation is real but attenuated, as in practice.
    true_risk = (0.040 * (lst_f - lst_f.mean())
                 + 0.055 * (pct_age65p - pct_age65p.mean())
                 + 0.030 * (pct_poverty - pct_poverty.mean())
                 - 0.022 * (pct_canopy - pct_canopy.mean()))
    zdf = pd.DataFrame({"zcta": tracts["ZCTA_mock"], "risk": true_risk,
                        "pop": tracts["pop"]})
    zagg = zdf.groupby("zcta").apply(
        lambda g: np.average(g["risk"], weights=g["pop"]), include_groups=False)
    er = pd.DataFrame({
        "zcta": zagg.index,
        "heat_er_rate_per100k": np.clip(
            22 + 6.5 * zagg.to_numpy()
            + rng.normal(0, 3.0, len(zagg)), 0.5, None).round(2),
    })

    # --- existing cooling centres -------------------------------------------
    # Placed with a mild bias towards populous, wealthier tracts: that is the
    # realistic status quo (civic buildings and libraries cluster downtown and
    # in established neighbourhoods), and it gives Part A something to detect.
    n_centers = (cfg.mock_n_centers_augmented if cfg.centers_set == "augmented"
                 else cfg.mock_n_centers_permanent)
    w = (pop / pop.sum()) * np.exp(0.35 * wealth)
    w = w / w.sum()
    pick = rng.choice(n, size=n_centers, replace=False, p=w)
    cpts = [Point(tracts["INTPTLON"].iloc[i] + rng.normal(0, cw / 4),
                  tracts["INTPTLAT"].iloc[i] + rng.normal(0, ch / 4)) for i in pick]
    centers = gpd.GeoDataFrame(
        {"center_id": [f"MOCK-{i:03d}" for i in range(1, n_centers + 1)],
         "name": [f"Mock Cooling Center {i}" for i in range(1, n_centers + 1)],
         "source": "synthetic"},
        geometry=cpts, crs=CRS_GEO)

    return {"tracts": tracts, "centers": centers, "er_zip": er}


def write_mock(cfg: Config) -> None:
    out = build_mock(cfg)
    raw = cfg.paths.raw / "mock"
    raw.mkdir(parents=True, exist_ok=True)
    out["tracts"].to_file(raw / "mock_tracts.gpkg", layer="tracts", driver="GPKG")
    out["centers"].to_file(raw / "mock_centers.gpkg", layer="centers", driver="GPKG")
    out["er_zip"].to_csv(raw / "mock_er_zip.csv", index=False)
