"""Member 3 - add the LA holdout predictions to the website's ZIP layer.

The site already carries the LA out-of-fold predictions (pred_poisson, pred_rf, pred_gbm).
The side-by-side and error views also need the LA holdout predictions, so that a viewer
can choose which prediction version is shown. This script adds them to the existing
site/data/zips.geojson without re-fetching any geometry (no network needed), and records
what each prediction source is in site/data/prediction_sources.json.

Sources (existing results; to be replaced by the final versions at integration)
  results/predictions_oof.csv         LA-only spatial cross-validation, heat level 4
  results/predictions_la_holdout.csv  trained on the rest of California; heat-level-4 rows

Adds to each ZIP feature:  hold_poisson, hold_rf, hold_gbm   (same units as the label)
Idempotent: running it twice gives the same file.

Run:  .venv/bin/python scripts/member3_add_site_predictions.py
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import pandas as pd

SITE = pathlib.Path("site/data")
LEVEL = 4
SHORT = {"poisson": "poisson", "random_forest": "rf", "gradient_boosting": "gbm"}


def sha(path: str) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()[:16]


def main() -> None:
    gj = json.loads((SITE / "zips.geojson").read_text())
    hold = pd.read_csv("results/predictions_la_holdout.csv")
    hold = hold[hold["chs_level"] == LEVEL].set_index("zip")
    oof = pd.read_csv("results/predictions_oof.csv").set_index("zip")

    n_hold = n_oof_ok = 0
    for f in gj["features"]:
        p = f["properties"]
        z = int(p["zip"])
        for long, short in SHORT.items():
            p[f"hold_{short}"] = (round(float(hold.at[z, f"pred_{long}"]), 2)
                                  if z in hold.index else None)
        n_hold += z in hold.index
        # consistency: the label and OOF values already on the site match the result files
        if z in oof.index:
            n_oof_ok += (abs(p["observed_rate"] - oof.at[z, "y_true"]) < 0.006
                         and abs(p["pred_poisson"] - oof.at[z, "pred_poisson"]) < 0.006)
            assert abs(hold.at[z, "excess_er_rate_per_10k"] - p["observed_rate"]) < 0.051, z
    assert n_hold == len(gj["features"]), "every mapped ZIP needs a holdout prediction"
    assert n_oof_ok == len(gj["features"]), "site label / OOF values differ from results/"
    (SITE / "zips.geojson").write_text(json.dumps(gj))

    sources = {
        "label": {
            "name": "UCLA label",
            "property": "observed_rate",
            "description": "UCLA Heat Maps estimated excess ER visits per 10,000 residents, "
                           "CalHeatScore level 4 layer, total over May-October 2008-2018",
            "unit": "excess ER visits per 10,000 residents (total, May-Oct 2008-2018)",
        },
        "sources": {
            "oof": {
                "name": "LA out-of-fold",
                "long_name": "LA out-of-fold predictions",
                "description": "Each ZIP is predicted by a model trained on the other four "
                               "spatial folds of LA County (heat level 4 only).",
                "properties": {"poisson": "pred_poisson", "random_forest": "pred_rf",
                               "gradient_boosting": "pred_gbm"},
                "file": "results/predictions_oof.csv", "sha256_16": sha("results/predictions_oof.csv"),
            },
            "holdout": {
                "name": "LA holdout",
                "long_name": "LA holdout predictions",
                "description": "Every LA ZIP is predicted by one model trained on all California "
                               "ZIPs outside LA County (heat levels 1-4); level-4 predictions shown.",
                "properties": {"poisson": "hold_poisson", "random_forest": "hold_rf",
                               "gradient_boosting": "hold_gbm"},
                "file": "results/predictions_la_holdout.csv",
                "sha256_16": sha("results/predictions_la_holdout.csv"),
            },
        },
        "models": {"poisson": "Poisson", "random_forest": "Random forest",
                   "gradient_boosting": "Gradient boosting"},
        "error_definition": "error = prediction - UCLA label; positive = overprediction, "
                            "negative = underprediction; same unit as the label",
        "status": "Development versions from the existing results at commit 0980d9a. "
                  "Replace with the final selected versions at integration.",
        "n_zips": len(gj["features"]), "heat_level": LEVEL,
    }
    (SITE / "prediction_sources.json").write_text(json.dumps(sources, indent=2))
    print(f"added holdout predictions to {n_hold} ZIP features; wrote prediction_sources.json")


if __name__ == "__main__":
    main()
