"""Step 3 - zoom ZIP risk down to census tracts (downscaling).

UCLA gives one excess-ER number per ZIP. A ZIP can hold very different neighborhoods.
We split each LA ZIP's REAL observed excess-ER *number* across its census tracts in
proportion to (model-predicted rate x tract population), so tract numbers sum back to
the real ZIP total. The model used for LA is trained on California EXCLUDING LA, so LA
tract weights come from a model that never saw LA (honest transfer).

There is no tract-level ground truth, so the split is validated indirectly:
  - Pseudo-ZIP test: merge each ZIP's tracts into groups, treat the group total as the
    only known value, split it back to member tracts' parent ZIPs with the model, and
    compare the recovered ZIP numbers to the real ZIP numbers.
  - Baseline to beat: split by population only (everyone equally at risk per person).

Writes:
  data/processed/tract_features_la.csv - LA tracts with CES features (untouched join)
  results/tract_risk_la.csv            - per-tract estimated excess-ER number + rate
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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from heatla import model as M  # noqa: E402
from run_models_ca import FEATURES, TARGET, load  # reuse feature list + loader  # noqa: E402

RES = pathlib.Path("results")
PROC = pathlib.Path("data/processed")
CHS = 4  # downscale the extreme-heat (CHS-4) excess ER

# CES tract raw field -> model feature name (same mapping as fetch_statewide)
CES_MAP = {
    "PM2_5": "pm25", "Ozone": "ozone", "Asthma": "asthma_ed_per10k",
    "Cardiovas": "cardiovascular_ed_per10k", "Poverty": "poverty_pct",
    "Elderly65": "elderly65_pct", "Educatn": "edu_lt_hs_pct", "Ling_Isol": "ling_isol_pct",
    "Unempl": "unemployment_pct", "HousBurd": "housing_burden_pct",
}


def la_tracts(la_zips: set[str]) -> pd.DataFrame:
    """LA tracts = CES tracts whose ZIP is an LA-County ZIP (County/Tract were not
    pulled into the raw file; we identify LA by its ZIP set and synthesize a tract id)."""
    t = pd.read_csv("data/raw/ces40_ca_tracts.csv")
    t["zip"] = t["ZIP"].astype("Int64").astype(str).str.zfill(5)
    t = t[t["zip"].isin(la_zips)].copy().reset_index(drop=True)
    t["Tract"] = t["zip"] + "-" + (t.groupby("zip").cumcount() + 1).astype(str)
    t = t.rename(columns=CES_MAP)
    t["pop"] = pd.to_numeric(t["TotPop19"], errors="coerce")
    for c in CES_MAP.values():
        t[c] = pd.to_numeric(t[c], errors="coerce")
    return t


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
    tracts = tracts.dropna(subset=list(CES_MAP.values()) + ["pop", "zip_density"])
    tracts = tracts[tracts["pop"] > 0]
    tracts["pred_rate"] = predicted_tract_rate(model, tracts)
    tracts["weight"] = tracts["pred_rate"] * tracts["pop"]
    rows = []
    for z, g in tracts.groupby("zip"):
        total = zip_number.get(z)
        if total is None or g["weight"].sum() <= 0:
            continue
        share = g["weight"] / g["weight"].sum()
        est = share * total
        for (idx, tr), e, sr in zip(g.iterrows(), est, share):
            rows.append({"zip": z, "tract": tr["Tract"], "pop": tr["pop"],
                         "pred_rate": round(tr["pred_rate"], 3),
                         "est_excess_er_number": round(float(e), 3),
                         "est_rate_per_10k": round(float(e) / tr["pop"] * 1e4, 3)
                         if tr["pop"] > 0 else None,
                         "share_of_zip": round(float(sr), 4)})
    return pd.DataFrame(rows)


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
    return {
        "n_zips": int(len(la)), "n_groups": int(k),
        "mae_model_split": round(mae(true, est_model), 3),
        "mae_population_split": round(mae(true, est_pop), 3),
        "improvement_vs_population": round(
            1 - mae(true, est_model) / mae(true, est_pop), 4) if mae(true, est_pop) else None,
        "note": "lower MAE is better; model split beats population split iff mae_model < mae_pop",
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
    out.to_csv(RES / "tract_risk_la.csv", index=False)

    val = pseudo_zip_validation(model, df)
    (RES / "downscale_validation.json").write_text(json.dumps(val, indent=2))

    print(f"tracts estimated: {len(out)} across {out['zip'].nunique()} LA ZIPs")
    print("pseudo-ZIP validation:")
    print(f"  model split MAE     : {val['mae_model_split']}")
    print(f"  population split MAE : {val['mae_population_split']}")
    print(f"  improvement vs pop  : {val['improvement_vs_population']}")


if __name__ == "__main__":
    main()
