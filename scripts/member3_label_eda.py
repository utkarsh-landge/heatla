"""Member 3 - exploratory analysis of the UCLA labels by heat level.

Answers the professor's request: how large are the excess ER visits at each heat level,
with mean and standard deviation, and is there a jump at level 4?

It also documents how the label is built, because that changes how the levels should be
read. In the published layer the level-k value is CUMULATIVE: it covers every warm-season
day at or below level k (see reports/member3_labels_website_siting.md, section 1). The
contribution of level-k days alone is the difference between level k and level k-1.

Inputs (read-only)
  data/raw/ca_excess_er_zip.csv        UCLA zip_ER layer, all California, rate rows
  data/processed/model_table_ca.csv    used only to apply the same cleaning as the models
Outputs
  results/member3/label_eda/*.csv      tables
  results/member3/label_eda/*.png      figures

Run:  .venv/bin/python scripts/member3_label_eda.py
"""
from __future__ import annotations

import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

OUT = pathlib.Path("results/member3/label_eda")
LEVELS = (1, 2, 3, 4)
LA = "Los Angeles"
SEASON_DAYS = 184 * 11          # 1 May - 31 Oct, 2008-2018
UNIT = "excess ER visits per 10,000 residents, total over May-Oct 2008-2018"

INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
SURFACE, GRID, AXIS = "#fcfcfb", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE = "#2a78d6", "#eb6834"
plt.rcParams.update({
    "font.family": "sans-serif", "font.size": 9, "text.color": INK,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.facecolor": SURFACE,
    "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE, "xtick.color": AXIS,
    "ytick.color": AXIS, "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
    "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "legend.frameon": False})


def load() -> pd.DataFrame:
    """One row per ZIP with rate, day count and threshold at each level (cleaned ZIPs only)."""
    raw = pd.read_csv("data/raw/ca_excess_er_zip.csv")
    raw["zip"] = raw["zip"].astype(int).astype(str).str.zfill(5)
    assert set(raw["NumRate"]) == {"Rate"} and set(raw["Years"]) == {"2008-2018"}
    model = pd.read_csv("data/processed/model_table_ca.csv")
    model["zip"] = model["zip"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    clean = set(model.dropna(subset=["excess_er_rate_per_10k", "lat", "lon", "population"])["zip"])
    raw = raw[raw["zip"].isin(clean)]
    wide = raw.pivot(index="zip", columns="categry", values="excs_ER")
    wide.columns = [f"rate_L{c}" for c in wide.columns]
    days = raw.pivot(index="zip", columns="categry", values="n_ht_dy")
    days.columns = [f"days_upto_L{c}" for c in days.columns]
    first = raw.drop_duplicates("zip").set_index("zip")
    out = wide.join(days).join(first[["cnty_nm", "popultn", "lvl1_th", "lvl2_th", "lvl3_th", "lvl4_th"]])
    out = out.rename(columns={"cnty_nm": "county", "popultn": "population"})
    # contribution of each level alone = difference between consecutive cumulative values
    out["only_L1"] = out["rate_L1"]
    out["days_L0_and_L1"] = out["days_upto_L1"]
    for k in (2, 3, 4):
        out[f"only_L{k}"] = out[f"rate_L{k}"] - out[f"rate_L{k-1}"]
        out[f"days_L{k}"] = out[f"days_upto_L{k}"] - out[f"days_upto_L{k-1}"]
    return out.reset_index()


def describe(s: pd.Series) -> dict:
    return {"zips": int(s.notna().sum()), "mean": round(s.mean(), 2), "sd": round(s.std(), 2),
            "min": round(s.min(), 2), "p25": round(s.quantile(.25), 2),
            "median": round(s.median(), 2), "p75": round(s.quantile(.75), 2),
            "max": round(s.max(), 2), "cv": round(s.std() / s.mean(), 2)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    d = load()
    la = d[d["county"] == LA]
    regions = (("California", d), ("Los Angeles County", la))

    # ---- structural checks that support the cumulative reading
    checks = [
        {"check": "ZIPs analysed (same cleaning as the models)", "value": len(d)},
        {"check": "of which Los Angeles County", "value": len(la)},
        {"check": "ZIPs where the rate rises at every level (L1<=L2<=L3<=L4)",
         "value": int(((d.rate_L1 <= d.rate_L2) & (d.rate_L2 <= d.rate_L3)
                       & (d.rate_L3 <= d.rate_L4)).sum())},
        {"check": "ZIPs where the day count rises at every level",
         "value": int(((d.days_upto_L1 <= d.days_upto_L2) & (d.days_upto_L2 <= d.days_upto_L3)
                       & (d.days_upto_L3 <= d.days_upto_L4)).sum())},
        {"check": f"ZIPs whose level-4 day count equals all warm-season days ({SEASON_DAYS})",
         "value": int((d.days_upto_L4 == SEASON_DAYS).sum())},
        {"check": "Distinct level-4 temperature thresholds across ZIPs",
         "value": int(d.lvl4_th.nunique())},
        {"check": "ZIPs with a negative level-only contribution at any level",
         "value": int((d[[f"only_L{k}" for k in (2, 3, 4)]] < 0).any(axis=1).sum())},
    ]
    pd.DataFrame(checks).to_csv(OUT / "label_structure_checks.csv", index=False)

    # ---- Table A: the label as published (cumulative), by level
    rows = []
    for name, sub in regions:
        for k in LEVELS:
            rows.append({"region": name, "heat_level": k, "what": "published label (cumulative)",
                         **describe(sub[f"rate_L{k}"]),
                         "mean_days_covered": round(sub[f"days_upto_L{k}"].mean(), 0)})
    cum = pd.DataFrame(rows)
    for name, sub in regions:
        m = cum[cum.region == name].set_index("heat_level")["mean"]
        cum.loc[cum.region == name, "ratio_to_previous_level"] = [
            np.nan if k == 1 else round(m[k] / m[k - 1], 2) for k in LEVELS]
    cum.to_csv(OUT / "label_by_level_cumulative.csv", index=False)

    # ---- Table B: contribution of each level alone
    rows = []
    for name, sub in regions:
        for k in LEVELS:
            days = sub["days_L0_and_L1"] if k == 1 else sub[f"days_L{k}"]
            rows.append({"region": name, "heat_level": k,
                         "what": "level 1 and below" if k == 1 else f"level-{k} days only",
                         **describe(sub[f"only_L{k}"]),
                         "mean_days": round(days.mean(), 0),
                         "share_of_level4_total_pct":
                             round(100 * sub[f"only_L{k}"].sum() / sub["rate_L4"].sum(), 1)})
    inc = pd.DataFrame(rows)
    inc.to_csv(OUT / "label_by_level_increment.csv", index=False)

    # ---- thresholds and rank agreement between levels
    th = pd.DataFrame([{"region": n, "heat_level": k, **describe(s[f"lvl{k}_th"])}
                       for n, s in regions for k in LEVELS])
    th.to_csv(OUT / "temperature_thresholds_by_level.csv", index=False)
    d[[f"rate_L{k}" for k in LEVELS]].corr(method="spearman").round(3).to_csv(
        OUT / "spearman_between_levels_cumulative.csv")
    d[[f"only_L{k}" for k in LEVELS]].corr(method="spearman").round(3).to_csv(
        OUT / "spearman_between_levels_increment.csv")
    d.to_csv(OUT / "labels_wide_by_zip.csv", index=False)

    # ---- Figure 1: mean with SD whiskers by level (the professor's request)
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), sharey=True)
    x = np.arange(4); w = 0.38
    for ax, col, title in ((axes[0], "rate_L", "Label as published: all days at or below the level"),
                           (axes[1], "only_L", "Contribution of each level alone")):
        for j, (name, sub, color) in enumerate((("California", d, BLUE),
                                                ("Los Angeles County", la, ORANGE))):
            means = [sub[f"{col}{k}"].mean() for k in LEVELS]
            sds = [sub[f"{col}{k}"].std() for k in LEVELS]
            bars = ax.bar(x + (j - .5) * w, means, w - .04, color=color,
                          label=f"{name} ({len(sub):,} ZIPs)")
            ax.errorbar(x + (j - .5) * w, means, yerr=sds, fmt="none", ecolor=INK2,
                        elinewidth=1, capsize=3)
            for b, m, s in zip(bars, means, sds):
                ax.annotate(f"{m:.1f}", (b.get_x() + b.get_width() / 2, m + s),
                            xytext=(0, 3), textcoords="offset points", ha="center",
                            fontsize=7.5, color=INK2)
        labels = [f"Level {k}" for k in LEVELS] if col == "rate_L" else \
            ["Level 1\nand below", "Level 2\nonly", "Level 3\nonly", "Level 4\nonly"]
        ax.set_xticks(x, labels); ax.grid(True, axis="y"); ax.set_axisbelow(True)
        ax.set_title(title, loc="left", fontweight="bold", fontsize=10)
    axes[0].set_ylabel("Excess ER visits per 10,000")
    axes[0].legend(loc="upper left", fontsize=8.5)
    fig.suptitle("UCLA excess ER visits by heat level: mean, with whiskers showing ±1 standard "
                 "deviation across ZIPs", x=0.01, ha="left", fontsize=11, fontweight="bold")
    fig.text(0.01, 0.905, "Totals over the warm seasons (May–October) of 2008–2018, per 10,000 "
             "residents.", fontsize=8.5, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(OUT / "label_mean_sd_by_level.png", dpi=160, bbox_inches="tight"); plt.close(fig)

    # ---- Figure 2: full distributions by level
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))
    for ax, (name, sub, color) in zip(axes, (("California", d, BLUE),
                                             ("Los Angeles County", la, ORANGE))):
        data = [sub[f"rate_L{k}"].to_numpy() for k in LEVELS]
        bp = ax.boxplot(data, positions=range(4), widths=0.55, patch_artist=True,
                        showfliers=True, flierprops=dict(marker="o", ms=2.5, mfc=color,
                                                         mec="none", alpha=0.45),
                        medianprops=dict(color=INK, lw=1.4),
                        whiskerprops=dict(color=INK2), capprops=dict(color=INK2))
        for b in bp["boxes"]:
            b.set(facecolor=color, alpha=0.55, edgecolor=INK2)
        ax.set_xticks(range(4), [f"Level {k}" for k in LEVELS]); ax.grid(True, axis="y")
        ax.set_axisbelow(True)
        ax.set_title(f"{name} ({len(sub):,} ZIPs)", loc="left", fontweight="bold", fontsize=10)
        ax.set_ylabel("Excess ER visits per 10,000")
    fig.suptitle("Distribution of the published label across ZIPs, by heat level",
                 x=0.01, ha="left", fontsize=11, fontweight="bold")
    fig.text(0.01, 0.905, "Box = middle half of ZIPs, line = median, whiskers = 1.5 × "
             "interquartile range, points = ZIPs beyond the whiskers. Axes differ between panels.",
             fontsize=8.5, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(OUT / "label_distribution_by_level.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    pd.set_option("display.width", 250)
    print(pd.DataFrame(checks).to_string(index=False))
    print(cum.to_string(index=False)); print(inc.to_string(index=False))
    print(th.to_string(index=False))
    print(pd.read_csv(OUT / "spearman_between_levels_cumulative.csv").to_string(index=False))
    print(pd.read_csv(OUT / "spearman_between_levels_increment.csv").to_string(index=False))


if __name__ == "__main__":
    main()
