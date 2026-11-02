"""Step 5b - project each LA ZIP's extreme-heat excess-ER rate to a ~2030 window.

Method (documented, no fabrication):

    excess_ER_2030(zip) = observed_excess_ER(zip) * heat_factor(zip)

    heat_factor(zip) = mean extreme-heat-days 2026-2035  (Cal-Adapt, scenario)
                       -------------------------------------------------------
                       mean extreme-heat-days 2008-2018  (Cal-Adapt, SAME series)

- observed_excess_ER = UCLA Heat Maps CHS-4 excess-ER rate per 10,000 (the real
  observed target, data/processed/target.csv). This is the quantity being scaled.
- heat_factor uses the SAME Cal-Adapt ens32avg series for numerator and denominator
  (same 32 models, same 98th-percentile definition), so the ratio has no
  historical/projection splice. 2008-2018 matches the UCLA observation window.
- 2026-2035 is a 10-year window centred on 2030 (climate is reported as multi-year
  averages, never a single year).

Assumptions, stated honestly:
  * Per-heat-day vulnerability is held constant: only the number of extreme-heat days
    changes, not how many ER visits each heat day causes. Demographics/health
    (CES, ACS) are today's; they are NOT projected (that would be fabrication).
  * The factor is a multiplicative climate signal, not a fitted time-series model
    (there is no per-ZIP yearly ER series to fit).

Outputs:
  data/processed/heat_factor_2030.csv   - zip, scenario, base_days, fut_days, heat_factor
  results/projection_2030.json          - per scenario: ranked ZIPs, summary stats
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd

PROC = pathlib.Path("data/processed")
RES = pathlib.Path("results")
BASE_YEARS = (2008, 2018)
FUT_YEARS = (2026, 2035)
FUT_LABEL = "2026-2035 (centred on 2030)"


def main() -> None:
    h = pd.read_csv(PROC / "heat_days_la.csv", dtype={"zip": str})
    tgt = pd.read_csv(PROC / "target.csv", dtype={"zip": str})
    tgt["zip"] = tgt["zip"].str.zfill(5)
    obs = tgt.set_index("zip")["excess_er_rate_per_10k"]

    factors = []
    out = {"method": "excess_ER_2030 = observed_excess_ER * heat_factor",
           "heat_factor": "mean exheat days 2026-2035 / mean exheat days 2008-2018, "
                          "Cal-Adapt ens32avg (32 LOCA models)",
           "base_window": list(BASE_YEARS), "future_window": FUT_LABEL,
           "observed_source": "UCLA Heat Maps CHS-4 excess-ER rate per 10,000",
           "scenarios": {}}

    for scen in ["rcp45", "rcp85"]:
        d = h[h.scenario == scen]
        base = d[d.year.between(*BASE_YEARS)].groupby("zip").extreme_heat_days.mean()
        fut = d[d.year.between(*FUT_YEARS)].groupby("zip").extreme_heat_days.mean()
        hf = (fut / base).rename("heat_factor")
        df = pd.concat([base.rename("base_days"), fut.rename("fut_days"), hf], axis=1)
        df["scenario"] = scen
        df["observed_rate"] = obs.reindex(df.index)
        df["projected_rate_2030"] = df["observed_rate"] * df["heat_factor"]
        df = df.reset_index()
        factors.append(df)

        ranked = (df.dropna(subset=["projected_rate_2030"])
                    .sort_values("projected_rate_2030", ascending=False))
        out["scenarios"][scen] = {
            "n_zips": int(df["heat_factor"].notna().sum()),
            "n_projected": int(df["projected_rate_2030"].notna().sum()),
            "heat_factor_median": round(float(hf.median()), 3),
            "heat_factor_min": round(float(hf.min()), 3),
            "heat_factor_max": round(float(hf.max()), 3),
            "observed_rate_mean": round(float(df["observed_rate"].mean()), 2),
            "projected_rate_mean_2030": round(float(df["projected_rate_2030"].mean()), 2),
            "mean_increase_pct": round(float(
                (df["projected_rate_2030"].mean() / df["observed_rate"].mean() - 1) * 100), 1),
            "top15_zips": [
                {"zip": r.zip, "observed_rate": round(r.observed_rate, 1),
                 "heat_factor": round(r.heat_factor, 2),
                 "projected_rate_2030": round(r.projected_rate_2030, 1)}
                for r in ranked.head(15).itertuples(index=False)],
        }

    allf = pd.concat(factors, ignore_index=True)
    allf.to_csv(PROC / "heat_factor_2030.csv", index=False)
    (RES / "projection_2030.json").write_text(json.dumps(out, indent=2))

    print(f"wrote {PROC/'heat_factor_2030.csv'} ({len(allf)} rows) and "
          f"{RES/'projection_2030.json'}")
    for scen in ["rcp45", "rcp85"]:
        s = out["scenarios"][scen]
        print(f"  {scen}: factor median {s['heat_factor_median']}x "
              f"({s['heat_factor_min']}-{s['heat_factor_max']}), "
              f"mean rate {s['observed_rate_mean']} -> {s['projected_rate_mean_2030']} "
              f"(+{s['mean_increase_pct']}%)")


if __name__ == "__main__":
    main()
