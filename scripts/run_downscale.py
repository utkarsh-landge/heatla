"""Step 3 - zoom ZIP risk down to census tracts (downscaling).

UCLA gives one excess-ER number per ZIP. A ZIP can hold very different neighborhoods.
We split each LA ZIP's REAL observed excess-ER *number* across its census tracts in
proportion to (model-predicted rate x tract population), so tract numbers sum back to
the real ZIP total. The model used for LA is trained on California EXCLUDING LA, so LA
tract weights come from a model that never saw LA (honest transfer).

Inputs are the corrected ones: the model is trained on
data/corrected/model_table_ca_corrected.csv (CalEnviroScreen -999 treated as missing
before ZIP aggregation), and at tract level -999 is also treated as missing
(heatla.ces.to_value). Missing tract inputs are filled by the model's own imputer
(training-set median), the same way missing ZIP inputs are handled in modeling.

Tracts are real 2020 census tracts (11-digit GEOID):
  1. CES 4.0 is on 2010 tracts. data/raw/ces40_ca_tracts.csv has no tract ID column,
     so each row is matched to the OEHHA full file (data/raw/heatrisk/ces4_ca.csv,
     which has the ID) on population + PM2.5 + ozone; that key is unique in both files.
  2. 2010 -> 2020 tracts (data/raw/heatrisk/xwalk_tract10_20_ca.csv): a 2010 tract's
     TotPop19 is shared across its 2020 pieces by land-area share; a 2020 tract's CES
     inputs are the population-weighted mean of its 2010 pieces' values.
  3. 2020 tract -> ZIP (data/raw/heatrisk/xwalk_zcta_tract_ca.csv, Census 2020
     ZCTA-tract relationship): a tract that crosses ZIP lines is cut into pieces; each
     piece gets the tract's population times its land-area share and belongs to one ZIP.
  Area shares assume people are spread evenly over land within a tract.

There is no tract-level ground truth, so the split is validated indirectly:
  - Pseudo-ZIP test: merge each ZIP's tracts into groups, treat the group total as the
    only known value, split it back to member tracts' parent ZIPs with the model, and
    compare the recovered ZIP numbers to the real ZIP numbers.
  - Baseline to beat: split by population only (everyone equally at risk per person).

Writes:
  results/tract_risk_la.csv            - one row per (2020 tract, ZIP) piece: estimated
                                         excess-ER number + rate; pieces sum to the ZIP
  results/tract_risk_la_by_tract.csv   - pieces summed to one row per 2020 tract (for maps)
  results/downscale_validation.json    - model split vs population-only split
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from heatla import model as M  # noqa: E402
from heatla.ces import to_value  # noqa: E402
from run_models_ca import FEATURES, TARGET  # reuse feature list  # noqa: E402

RES = pathlib.Path("results")
PROC = pathlib.Path("data/processed")
CHS = 4  # downscale the extreme-heat (CHS-4) excess ER
CA_TABLE = pathlib.Path("data/corrected/model_table_ca_corrected.csv")  # -999 corrected
CES_TRACTS = pathlib.Path("data/raw/ces40_ca_tracts.csv")
CES_FULL = pathlib.Path("data/raw/heatrisk/ces4_ca.csv")              # has tract IDs
XW_10_20 = pathlib.Path("data/raw/heatrisk/xwalk_tract10_20_ca.csv")
XW_ZCTA = pathlib.Path("data/raw/heatrisk/xwalk_zcta_tract_ca.csv")

# CES tract raw field -> model feature name (same mapping as fetch_statewide)
CES_MAP = {
    "PM2_5": "pm25", "Ozone": "ozone", "Asthma": "asthma_ed_per10k",
    "Cardiovas": "cardiovascular_ed_per10k", "Poverty": "poverty_pct",
    "Elderly65": "elderly65_pct", "Educatn": "edu_lt_hs_pct", "Ling_Isol": "ling_isol_pct",
    "Unempl": "unemployment_pct", "HousBurd": "housing_burden_pct",
}


def load() -> pd.DataFrame:
    """Corrected statewide ZIP table, parsed exactly like run_models_ca.load()."""
    df = pd.read_csv(CA_TABLE)
    for c in FEATURES + [TARGET, "lat", "lon", "population"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=[TARGET, "lat", "lon", "population"]).reset_index(drop=True)
    df["zip"] = df["zip"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    return df


def ces_tracts_2010() -> pd.DataFrame:
    """CES 4.0 tract inputs with their real 2010 tract GEOID; -999 -> NaN."""
    t = pd.read_csv(CES_TRACTS)
    full = pd.read_csv(CES_FULL, encoding="utf-8-sig", usecols=["tract", "ACS2019TotalPop",
                                                                 "pm", "ozone"])
    key = lambda pop, pm, oz: list(zip(pop, pm.round(4), oz.round(5)))  # noqa: E731
    t["k"] = key(t["TotPop19"], t["PM2_5"], t["Ozone"])
    full["k"] = key(full["ACS2019TotalPop"], full["pm"], full["ozone"])
    assert not t["k"].duplicated().any() and not full["k"].duplicated().any()
    t = t.merge(full[["k", "tract"]], on="k", how="left", validate="one_to_one")
    assert t["tract"].notna().all(), "CES row without a tract ID match"
    t["geoid10"] = t["tract"].astype("int64").astype(str).str.zfill(11)
    t = t.rename(columns=CES_MAP)
    t["pop"] = pd.to_numeric(t["TotPop19"], errors="coerce")
    for c in CES_MAP.values():
        t[c] = t[c].map(to_value).astype(float)
    return t[["geoid10", "pop"] + list(CES_MAP.values())]


def to_2020_tracts(t10: pd.DataFrame) -> pd.DataFrame:
    """2010 CES tracts -> 2020 tracts. Population moves by land-area share; inputs are the
    population-weighted mean of the 2010 pieces (a missing value is left out with its weight)."""
    xw = pd.read_csv(XW_10_20, dtype=str)
    for c in ("AREALAND_TRACT_10", "AREALAND_PART"):
        xw[c] = xw[c].astype(float)
    n = xw.groupby("GEOID_TRACT_10")["GEOID_TRACT_20"].transform("size")
    xw["share"] = np.where(xw["AREALAND_TRACT_10"] > 0,
                           xw["AREALAND_PART"] / xw["AREALAND_TRACT_10"], 1.0 / n)
    m = xw.merge(t10, left_on="GEOID_TRACT_10", right_on="geoid10", how="inner")
    m["w"] = m["pop"] * m["share"]
    out = m.groupby("GEOID_TRACT_20").agg(pop=("w", "sum"))
    for c in CES_MAP.values():
        ok = m[c].notna()
        num = (m[c].where(ok, 0) * m["w"]).groupby(m["GEOID_TRACT_20"]).sum()
        den = m["w"].where(ok, 0).groupby(m["GEOID_TRACT_20"]).sum()
        out[c] = (num / den).where(den > 0)
    return out.rename_axis("tract_geoid").reset_index()


def la_tracts(la_zips: set[str]) -> pd.DataFrame:
    """(2020 tract, ZIP) pieces for LA ZIPs. A tract's population is split across the
    ZIPs it touches by land-area share; each piece carries the tract's CES inputs."""
    t20 = to_2020_tracts(ces_tracts_2010())
    xw = pd.read_csv(XW_ZCTA, dtype=str)
    xw["part"] = xw["AREALAND_PART"].astype(float)
    # share of the tract's land that falls in each ZCTA (normalised over ZCTA parts)
    xw["area_share"] = xw["part"] / xw.groupby("GEOID_TRACT_20")["part"].transform("sum")
    xw = xw[xw["GEOID_ZCTA5_20"].isin(la_zips)]
    p = xw.merge(t20, left_on="GEOID_TRACT_20", right_on="tract_geoid", how="inner")
    p["zip"] = p["GEOID_ZCTA5_20"]
    p["tract_pop"] = p["pop"]
    p["pop"] = p["tract_pop"] * p["area_share"]
    return p[["tract_geoid", "zip", "area_share", "tract_pop", "pop"]
             + list(CES_MAP.values())].reset_index(drop=True)


def train_non_la(df: pd.DataFrame):
    """Poisson trained on CA minus LA (primary), for honest LA transfer."""
    tr = df[df["county"] != "Los Angeles"]
    model = M.make_models()["poisson"]
    model.fit(tr[FEATURES], tr[TARGET].to_numpy(float),
              glm__sample_weight=tr["population"].to_numpy(float))
    return model


def predicted_tract_rate(model, t: pd.DataFrame) -> np.ndarray:
    X = pd.DataFrame(index=t.index)
    X["chs_level"] = CHS
    for f in CES_MAP.values():
        X[f] = t[f]
    # tract-level density unknown here; use ZIP density as the tract's (shared within ZIP)
    X["pop_density_per_sqmi"] = t["zip_density"]
    X = X[FEATURES]
    return np.clip(model.predict(X), 0, None)


def downscale(model, tracts: pd.DataFrame, zip_number: dict[str, float],
              zip_density: dict[str, float]) -> pd.DataFrame:
    tracts = tracts.copy()
    tracts["zip_density"] = tracts["zip"].map(zip_density)
    # missing CES inputs are left for the model's imputer; only population/density required
    tracts = tracts.dropna(subset=["pop", "zip_density"])
    tracts = tracts[tracts["pop"] > 0]
    tracts["pred_rate"] = predicted_tract_rate(model, tracts)
    tracts["weight"] = tracts["pred_rate"] * tracts["pop"]
    rows = []
    for z, g in tracts.groupby("zip"):
        total = zip_number.get(z)
        if total is None or pd.isna(total) or g["weight"].sum() <= 0:
            continue
        share = g["weight"] / g["weight"].sum()
        est = share * total
        for (idx, tr), e, sr in zip(g.iterrows(), est, share):
            rows.append({"tract_geoid": tr["tract_geoid"], "zip": z,
                         "tract_area_share_in_zip": round(float(tr["area_share"]), 4),
                         "pop": round(float(tr["pop"]), 1),
                         "pred_rate": round(tr["pred_rate"], 3),
                         "est_excess_er_number": round(float(e), 3),
                         "est_rate_per_10k": round(float(e) / tr["pop"] * 1e4, 3)
                         if tr["pop"] > 0 else None,
                         "share_of_zip": round(float(sr), 4),
                         "_est": float(e)})
    return pd.DataFrame(rows)


def by_tract(out: pd.DataFrame) -> pd.DataFrame:
    """Sum the (tract, ZIP) pieces to one row per 2020 tract."""
    g = out.groupby("tract_geoid").agg(n_zips=("zip", "nunique"),
                                       zips=("zip", lambda z: ";".join(sorted(z))),
                                       pop=("pop", "sum"), est=("_est", "sum"))
    g["est_excess_er_number"] = g["est"].round(3)
    g["est_rate_per_10k"] = (g["est"] / g["pop"] * 1e4).round(3)
    g["pop"] = g["pop"].round(1)
    return g.drop(columns="est").reset_index()


def pseudo_zip_validation(model, df: pd.DataFrame) -> dict:
    """Hide real ZIP numbers inside spatial groups of ZIPs; recover them.

    Group LA ZIPs into clusters; treat each cluster's total observed excess-ER number as
    the only known value; split it back to member ZIPs by (pred_rate x pop) and, as a
    baseline, by population only. Compare both to the true per-ZIP numbers.
    """
    la = df[(df["county"] == "Los Angeles") & (df["chs_level"] == CHS)].copy()
    la = la.dropna(subset=["excess_er_number", "population", "lat", "lon"])
    la = la[la["population"] > 0].reset_index(drop=True)
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    k = max(2, len(la) // 6)
    xy = StandardScaler().fit_transform(la[["lat", "lon"]].to_numpy())
    la["grp"] = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(xy)
    la["pred_rate"] = np.clip(model.predict(la[FEATURES]), 0, None)
    la["w_model"] = la["pred_rate"] * la["population"]

    true, est_model, est_pop = [], [], []
    for _, g in la.groupby("grp"):
        tot = g["excess_er_number"].sum()
        wm = g["w_model"].sum()
        wp = g["population"].sum()
        for _, r in g.iterrows():
            true.append(r["excess_er_number"])
            est_model.append(tot * (r["w_model"] / wm) if wm > 0 else 0.0)
            est_pop.append(tot * (r["population"] / wp) if wp > 0 else 0.0)
    true, est_model, est_pop = map(lambda a: np.asarray(a, float), (true, est_model, est_pop))

    def mae(a, b): return float(np.mean(np.abs(a - b)))
    def rho(a, b): return round(float(spearmanr(a, b).statistic), 4)
    return {
        "n_zips": int(len(la)), "n_groups": int(k),
        "mae_model_split": round(mae(true, est_model), 3),
        "mae_population_split": round(mae(true, est_pop), 3),
        "improvement_vs_population": round(
            1 - mae(true, est_model) / mae(true, est_pop), 4) if mae(true, est_pop) else None,
        "spearman_model_split": rho(true, est_model),
        "spearman_population_split": rho(true, est_pop),
        "note": "lower MAE is better; model split beats population split iff mae_model < mae_pop. "
                "Spearman is the rank correlation of recovered vs real ZIP excess-ER numbers.",
    }


def main() -> None:
    RES.mkdir(parents=True, exist_ok=True)
    df = load()
    model = train_non_la(df)

    la4 = df[(df["county"] == "Los Angeles") & (df["chs_level"] == CHS)]
    zip_number = dict(zip(la4["zip"], la4["excess_er_number"]))
    zip_density = dict(zip(la4["zip"], la4["pop_density_per_sqmi"]))

    tracts = la_tracts(set(la4["zip"]))
    out = downscale(model, tracts, zip_number, zip_density)
    # every downscaled ZIP's pieces must add back to its UCLA number
    sums = out.groupby("zip")["_est"].sum()
    max_err = float((sums - sums.index.map(zip_number)).abs().max())
    assert max_err < 1e-6, max_err
    out.drop(columns="_est").to_csv(RES / "tract_risk_la.csv", index=False)
    per_tract = by_tract(out)
    per_tract.to_csv(RES / "tract_risk_la_by_tract.csv", index=False)

    val = pseudo_zip_validation(model, df)
    val["tract_output"] = {
        "tract_vintage": "2020 census tracts (CES 4.0 2010 tracts moved by land-area share)",
        "n_tracts": int(per_tract["tract_geoid"].nunique()),
        "n_tract_zip_pieces": int(len(out)),
        "n_tracts_split_across_zips": int((per_tract["n_zips"] > 1).sum()),
        "n_zips_downscaled": int(out["zip"].nunique()),
        "n_la_zips_in_table": int(len(la4)),
        "max_abs_zip_sum_error": max_err,
    }
    (RES / "downscale_validation.json").write_text(json.dumps(val, indent=2))

    print(f"tract pieces estimated: {len(out)} ({val['tract_output']['n_tracts']} 2020 tracts)"
          f" across {out['zip'].nunique()} of {len(la4)} LA ZIPs; max ZIP sum error {max_err:.2e}")
    print("pseudo-ZIP validation:")
    print(f"  model split MAE     : {val['mae_model_split']}")
    print(f"  population split MAE : {val['mae_population_split']}")
    print(f"  improvement vs pop  : {val['improvement_vs_population']}")
    print(f"  Spearman model / pop : {val['spearman_model_split']} / "
          f"{val['spearman_population_split']}")


if __name__ == "__main__":
    main()
