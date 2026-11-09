"""Member 1 - build the statewide table with a LEVEL-ONLY target.

Why
  In UCLA's published layer the heat-level-k value is cumulative: it covers every
  warm-season day at or below level k (Member 3's finding; an inference from the data,
  not stated by UCLA). The level-4 row is therefore the total over ALL heat levels, not
  the excess on extreme-heat days. The excess on level-k days alone is the difference
  between consecutive levels:

      level_only(k) = label(k) - label(k-1)   for k = 2, 3, 4
      level_only(1) = label(1)                (level 1 and below; nothing to subtract)

  The project's question is about extreme heat, so the quantity that answers it is
  level_only(4) = label(4) - label(3).

What it builds
  data/processed/model_table_ca_ces40_fixed_level_only.csv
  Identical to data/processed/model_table_ca_ces40_fixed.csv (sentinel-corrected CES 4.0
  inputs) except that excess_er_rate_per_10k holds the level-only value. The published
  cumulative value is kept in excess_er_rate_per_10k_cumulative. Inputs, rows and row
  order are unchanged, so folds and samples are the same as in the cumulative runs.
  A copy is saved in results/member1/inputs/.

Run:  .venv/bin/python scripts/build_member1_level_only_table.py
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

SRC = pathlib.Path("data/processed/model_table_ca_ces40_fixed.csv")
OUT = pathlib.Path("data/processed/model_table_ca_ces40_fixed_level_only.csv")
COPY = pathlib.Path("results/member1/inputs") / OUT.name
CHECK = pathlib.Path("results/member1/input_checks/level_only_target_checks.csv")
TARGET = "excess_er_rate_per_10k"


def main() -> None:
    df = pd.read_csv(SRC, dtype={"zip": str})
    df["_row"] = np.arange(len(df))
    wide = df.pivot(index="zip", columns="chs_level", values=TARGET)
    assert list(wide.columns) == [1, 2, 3, 4]
    only = wide.copy()
    for k in (2, 3, 4):
        only[k] = wide[k] - wide[k - 1]
    long = only.stack(future_stack=True).rename("level_only").reset_index()
    df = df.merge(long, on=["zip", "chs_level"], how="left").sort_values("_row")
    df[f"{TARGET}_cumulative"] = df[TARGET]
    df[TARGET] = df["level_only"].round(4)
    df = df.drop(columns=["level_only", "_row"])

    src = pd.read_csv(SRC, dtype={"zip": str})
    same_cols = [c for c in src.columns if c != TARGET]
    pd.testing.assert_frame_equal(df[same_cols].reset_index(drop=True), src[same_cols])
    assert np.allclose(df[f"{TARGET}_cumulative"], src[TARGET], equal_nan=True)
    df.to_csv(OUT, index=False)
    COPY.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(COPY, index=False)

    ok = df.dropna(subset=[TARGET, "lat", "lon", "population"])
    rows = []
    for name, sub in (("California", ok), ("Los Angeles County", ok[ok.county == "Los Angeles"])):
        for k in (1, 2, 3, 4):
            s = sub.loc[sub.chs_level == k, TARGET]
            c = sub.loc[sub.chs_level == k, f"{TARGET}_cumulative"]
            rows.append({"region": name, "heat_level": k, "zips": int(len(s)),
                         "level_only_mean": round(s.mean(), 2), "level_only_sd": round(s.std(), 2),
                         "level_only_min": round(s.min(), 2), "level_only_max": round(s.max(), 2),
                         "negative_values": int((s < 0).sum()), "zero_values": int((s == 0).sum()),
                         "cumulative_mean": round(c.mean(), 2), "cumulative_sd": round(c.std(), 2)})
    chk = pd.DataFrame(rows)
    CHECK.parent.mkdir(parents=True, exist_ok=True)
    chk.to_csv(CHECK, index=False)
    # the four level-only values of a ZIP must add back up to its level-4 label
    back = ok.pivot(index="zip", columns="chs_level", values=TARGET).sum(axis=1)
    l4 = ok[ok.chs_level == 4].set_index("zip")[f"{TARGET}_cumulative"]
    assert np.allclose(back, l4.loc[back.index], atol=1e-6)
    pd.set_option("display.width", 220)
    print(chk.to_string(index=False))
    print(f"wrote {OUT} and {COPY}; level-only values sum back to the level-4 label in "
          f"{len(back)} ZIPs")


if __name__ == "__main__":
    main()
