# Part 2 follow-up: level-4-only target and no ER-rate inputs

Part 1 raised two questions that the main Part 2 comparison did not test:

1. UCLA's level-4 label totals every heat level. The excess on level-4 days alone is label(4) − label(3). Does the LA-only comparison hold for that target?
2. Two inputs, the asthma and heart-attack ER-visit rates, come from the same state ER records as the label. What happens without them?

This repeats the controlled base-versus-augmented comparison four ways. Everything else is unchanged: the same 287 LA ZIPs, the same five spatial folds, models, settings, seed, preprocessing and metrics (imported from `run_feature_comparison.py`). Level-4-only values come from Member 1's table (`results/member1/inputs/model_table_ca_ces40_fixed_level_only.csv`). In LA they average 3.11 per 10,000 (SD 1.68), against 10.04 for the published label.

| Variant | Target | Inputs (base / augmented) |
|---|---|---|
| Cumulative | Published level-4 label | 11 / 15 (reproduces the main run) |
| Level-4 only | label(4) − label(3) | 11 / 15 |
| Cumulative, no ER rates | Published level-4 label | 9 / 13 |
| Level-4 only, no ER rates | label(4) − label(3) | 9 / 13 |

120 model fits. Output: `results/followup/`. Run: `python part2/run_followup_experiments.py` (about 20 seconds). The cumulative rerun matches the main run to within 0.002 in Spearman ρ (Poisson exactly; tree models differ slightly between operating systems).

## Results (all 287 ZIPs)

| Variant | Model | ρ base | ρ augmented | R² base | R² augmented | Top-10% base | Top-10% augmented |
|---|---|---|---|---|---|---|---|
| Cumulative | Poisson | 0.718 | 0.780 | 0.403 | 0.483 | 0.34 | 0.34 |
| Cumulative | Random forest | 0.685 | 0.710 | 0.421 | 0.461 | 0.17 | 0.21 |
| Cumulative | Gradient boosting | 0.719 | 0.731 | 0.426 | 0.468 | 0.31 | 0.28 |
| Level-4 only | Poisson | 0.637 | 0.648 | 0.328 | 0.022 | 0.45 | 0.38 |
| Level-4 only | Random forest | 0.673 | 0.662 | 0.398 | 0.370 | 0.41 | 0.38 |
| Level-4 only | Gradient boosting | 0.643 | 0.617 | 0.330 | 0.209 | 0.38 | 0.31 |
| Cumulative, no ER rates | Poisson | 0.553 | 0.691 | 0.240 | 0.117 | 0.28 | 0.34 |
| Cumulative, no ER rates | Random forest | 0.592 | 0.653 | 0.319 | 0.398 | 0.24 | 0.17 |
| Cumulative, no ER rates | Gradient boosting | 0.637 | 0.661 | 0.364 | 0.400 | 0.31 | 0.28 |
| Level-4 only, no ER rates | Poisson | 0.275 | 0.424 | 0.040 | −3.061 | 0.28 | 0.14 |
| Level-4 only, no ER rates | Random forest | 0.428 | 0.472 | 0.171 | 0.124 | 0.28 | 0.14 |
| Level-4 only, no ER rates | Gradient boosting | 0.364 | 0.411 | 0.090 | 0.009 | 0.24 | 0.21 |

Top-10% recall is computed on 29 ZIPs, so 0.03 is one ZIP.

**CalEnviroScreen percentile on the same 273 ZIPs:**

| Variant | CES percentile ρ | Augmented Poisson ρ | CES top-10% | Augmented Poisson top-10% |
|---|---|---|---|---|
| Cumulative | 0.566 | 0.811 | 0.15 | 0.33 |
| Level-4 only | 0.498 | 0.674 | 0.19 | 0.41 |
| Cumulative, no ER rates | 0.566 | 0.716 | 0.15 | 0.37 |
| Level-4 only, no ER rates | 0.498 | 0.432 | 0.19 | 0.15 |

## Findings

- **On extreme-heat days alone, the four ACS features stop helping.** Rank correlation is about the same with or without them (Poisson 0.637 → 0.648; the tree models fall slightly), and R² drops. The gain reported in the main run is a gain on the total heat burden, not on extreme-heat days.
- **The models still beat the CalEnviroScreen index on extreme-heat days** while the ER-rate inputs are in: ρ 0.674 against 0.498 on the same ZIPs.
- **Without the ER-rate inputs, the ACS features matter more.** On the published label, Poisson rises from ρ 0.553 to 0.691 when they are added; the exploratory interval for that gain (0.06 to 0.18) excludes zero. They partly stand in for what the ER-rate inputs carried.
- **Without the ER-rate inputs, extreme-heat-day ranking in LA is no better than the index.** The best model reaches ρ 0.47, and augmented Poisson on the matched ZIPs (0.432) falls below the CalEnviroScreen percentile (0.498). This matches Part 1's statewide-to-LA result (ρ 0.502 against 0.498).
- **One ZIP drives the very negative R².** ZIP 90089 (USC campus) has 100% renter households and 100% households without a vehicle, far outside every other ZIP. Poisson's log link extrapolates to 48.8 against a label of 2.0. Several downtown ZIPs (90021, 90013) are also overpredicted. Rank metrics are not affected much; R² is. Random forest and gradient boosting do not extrapolate and stay near zero instead.

## Limits

These use the same five folds, so the exploratory intervals rest on five blocks. The level-4-only target relies on the cumulative reading of UCLA's levels, which fits every ZIP but is not stated by UCLA. Campus and institutional ZIPs (90089, 90095) are kept, as in the main run.
