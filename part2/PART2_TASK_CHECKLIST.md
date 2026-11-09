# Part 2 task checklist — 2026-11-08

Authority: `11_8 Task Allocation plan (2).pdf`, section 3 / Member 2, pages 5–8; shared standards on pages 1–2 and 10–11. This is a status audit, not a change to the allocation plan.

Legend: **Done** = supporting code/output checked; **Partial** = substantive work exists but an explicit required artifact or verification remains; **Not done** = no completed deliverable found; **Unverified** = not enough evidence to assess.

## Task 1 — Verify LA data and variable definitions — Partial

| Requirement | Status | Evidence / remainder |
|---|---|---|
| Check original LA inputs, target and sample | Done, with target-interpretation caveat | Original 13-feature set identified; 289 raw/287 retained; original target values retained. UCLA cumulative interpretation is not settled. |
| Definitions, denominators, sources, reference periods for every variable | Consolidated with two shared unknowns | FEATURE_COMPARISON_TABLE.md now documents all 19 distinct predictor fields across the three configurations. CES Elderly65 and UCLA population reference years remain unconfirmed, explicitly labelled rather than guessed. |
| Renter variable definition | Done | Occupied housing units, B25003 numerator/denominator. |
| No-vehicle definition | Done | Owner + renter no-vehicle counts / occupied housing units. |
| Uninsured definition | Done | Civilian noninstitutionalized population percentage. |
| Construction definition | Done | Employed residents age 16+, construction industry, not all outdoor occupations. |
| Supporting literature for added indicators | Partial — selected and integrated | Riley, Derakhshan, Scott and Hess selected by the user; reference list, feature mapping and English rationale added. Scott full text remains unreviewed; only publisher-abstract claims are used. |
| Explain proxy limitations | Done within verified scope | FEATURE_SELECTION_RATIONALE.md and SUPPORTING_LITERATURE.md distinguish direct ED evidence, AC-access mechanisms, individual/community scale and healthcare utilization. |
| Assess representativeness for 2008–2018 | Done as an assessment, not exact alignment | ACS 2022 mainly postdates the label; ACS 2018 is within its later portion. |
| Replace suitable historical inputs and rerun affected experiments | Done | Four additions replaced with ACS 2018 / 2014–2018; 30 fold fits completed. |
| Explain retained mismatches and interpretation | Done within known evidence | Unified table and report state known mixed periods, explicit unknown years, historical window and geographic-vintage limits. |
| Distinguish CES versus ACS poverty definitions | Done | Separate rows explicitly show CES below 2× poverty and original ACS below poverty; no substitution in the new pair. |

Evidence: ACS_VARIABLE_AND_YEAR_AUDIT.md, HISTORICAL_FEATURE_UPDATE.md, results/feature_audit.csv, input_manifest.json, PART2_MODEL_COMPARISON_REPORT.md.

## Task 2 — Correct mean baseline and document missing-value handling — Done

| Requirement | Status | Evidence |
|---|---|---|
| Fold baseline uses training labels only | Done | results/mean_baseline_predictions.csv; feature_comparison/predictions_oof.csv. |
| Verify baseline results | Done | R² −0.111100, RMSE 3.258794, MAE 2.643521; independently checked. |
| Document actual preprocessing | Done | Median imputation; standardization for Poisson only. |
| Confirm median fitting inside training fold | Done | Training-time assertions and feature_comparison/preprocessing_audit.csv. |
| Preserve missing source values, handle them during fitting | Done | Missing cells remain blank; no zero filling or ACS 2022 fallback. |
| Deliver implementation, results and explanation | Done | Runner, metrics, preprocessing audit and English report. |

## Task 3 — Define base and augmented configurations — Done locally; shared labels pending

| Requirement | Status | Evidence / remainder |
|---|---|---|
| Retain Model A's base sources | Done | Member 1 corrected CES 4.0 statewide input; exact hash recorded. |
| Add only the four specified ACS variables | Done | Base 11, augmented 15, identical common columns. |
| Remove total population as predictor | Done | Excluded from both feature lists. |
| Explain heat level is constant | Done | Category 4 only; heat-level predictor omitted. |
| Preserve population for rate-to-count use | Done | Population retained as metadata and Poisson fitting weight. No siting rerun is claimed. |
| Verify counts and update old 12/13 labels | Partial | Current Part 2 files/report correctly say 11/15. Repository main report and website are not updated. |

## Task 4 — Controlled feature comparison — Done

| Requirement | Status | Evidence |
|---|---|---|
| Same ZIPs and target labels | Done | 287 in both; validation checks common fields and original labels. |
| Same original geographic folds | Done | Groups 0–4 with 100/57/70/48/12 ZIPs. |
| Same algorithms, settings and evaluation | Done | Poisson, RF and GBM; fixed seed/settings; six configurations, 30 fits. |
| R², Spearman, top-10% recall | Done | metrics_all_287.csv and metrics_per_fold.csv. |
| Supplementary top-20% recall | Done | Reported even where worse. |
| Interpret additions jointly, not individually | Done | Explicit in report; no claim of per-feature causal effects. |

## Task 5 — Complete experimental setup table — Done

| Requirement | Status | Evidence / remainder |
|---|---|---|
| Training/test scope | Done | EXPERIMENTAL_SETUP_TABLE.md: LA-only held-out geographic group versus other four groups. |
| Category-4 target | Done | Unchanged UCLA label, with unresolved interpretation stated. |
| Unique ZIP and row counts | Done | 287 ZIPs / 287 rows per configuration. |
| Exclusion rules | Done | Setup table states 289 to 287, excludes 91123/91522 for missing coordinates, and retains rows with missing feature values. |
| Actual folds and counts | Done | Saved assignments, fold summary and polygon map. |
| Input lists for both configurations | Done | experiment_config.json and report. |
| Distinguish from whole-LA holdout | Done | Direct contrast in setup table: LA internal train/test versus non-LA train/all-LA test. |
| Deliver one complete setup table | Done | EXPERIMENTAL_SETUP_TABLE.md, also inserted into the generated English report. |

## Task 6 — Unified feature comparison table — Done locally, shared unknowns retained

| Requirement | Status | Evidence / remainder |
|---|---|---|
| Compare Model A base, original LA, new augmented inclusion | Done | Full inclusion table verified against source code and configuration: 11/13/15 predictors. |
| Include each feature's definition | Done | All 19 distinct fields have definitions, units and raw fields/formulas in FEATURE_COMPARISON_TABLE.md. |
| Include each source | Done | Per-configuration source columns distinguish statewide/LA CES aggregation, original/historical ACS and population-density numerator. |
| Include each reference period | Done with explicit unknowns | Known periods entered; two shared unknown reference years preserved. No claim that all source years are confirmed. |
| Final check against Member 1 field list | Checked against bf4c5bf; final integration pending | Current base matches audited list excluding constant heat level. Check again if shared branch changes. |

## Task 7 — Report figures and interpretation — Done locally

| Requirement | Status | Evidence / remainder |
|---|---|---|
| Reuse existing scatter/fold plotting work | Functional outputs done; literal reuse differs | New isolated plotting code uses existing polygon data and saved folds, rather than editing old plotting scripts. |
| LA five-fold map with counts, referenced in report | Done | figures/LA_spatial_folds.png and PDF; report lists it. |
| Metric comparison | Done | figures/model_comparison.png and PDF. |
| Scatter plots for both configurations | Done | figures/label_vs_prediction.png and PDF: six panels. |
| Error maps for both configurations | Done | figures/spatial_errors.png and PDF: six panels, common zero-centred scale. |
| Label-versus-prediction value maps for both configurations | Done | figures/label_prediction_maps.png and PDF: three algorithms × UCLA label/base/augmented, with one common colour scale. |
| Explain local-training comparison confounding | Done | Report explicitly states differing feature sources/settings prevent attributing differences solely to geography. |
| Full captions identifying setup, level, n and units for every figure | Done | FIGURE_CAPTIONS.md contains captions for all six figures, including validation design, category, sample, units, colour meanings and interpretation limits; inserted in the generated report. |

## Final independent submission checklist

| Deliverable | Status |
|---|---|
| Code and run instructions | Done locally |
| LA variable definitions and period documentation | Consolidated; two shared unknown years remain explicitly labelled |
| Supporting literature | Selected and integrated; Scott full-text review pending |
| Corrected baseline results | Done |
| Unified feature table | Done locally; final field-list check at team integration still required |
| Setup and model results | Done locally; consolidated setup table and results included in English report |
| Figures and captions | Done locally: six PNG/PDF figures and full captions |
| Complete LA methods/results/limitations text | English draft includes four citations, unified feature table, setup table and all six figures/captions; Scott full-text verification remains pending, with current claims limited to the verified abstract |

## Shared preparation and final integration obligations

| Shared item relevant to Part 2 | Status |
|---|---|
| Starting version, separate working directory, separate feature lists/results | Done |
| Raw/processed inputs, source records and hashes | Available locally; final portable team snapshot packaging pending |
| Python/dependencies/commands | Done; isolated environment and frozen dependencies recorded |
| Preserve original results | Done; original repo unchanged and new outputs isolated |
| Review course sample midterm/final reports | Unverified; no evidence checked here |
| Consistent metrics/error direction | Done locally; cross-branch tie-rule reconciliation pending |
| Complete per-experiment metadata | Setup table and full figure captions done locally |
| Reproducibility | Fresh isolated environment successfully ran this experiment; another-machine/clean-delivery-folder reproduction is unverified |
| GitHub delivery | Not done; no Part 2 commit/push/PR made |
| Final report/website integration | Not done; website export files prepared only |
| Team agreement on label interpretation | Pending shared decision; current labels unchanged |

Not part of the original mandatory Part 2 checklist: automatic removal of 106 overlap-flagged ZIPs; a mandatory 181-ZIP sensitivity experiment; an asthma/cardiovascular removal experiment; automatically changing the target to L4−L3; retraining all of Part 1; implementing Part 3's website changes. These require separate justification or team agreement.

The earlier 80% estimate was approximate. Training/comparison, selected-reference integration, the unified feature table, the experimental setup table and all six figures/full captions are complete locally. Remaining source verification and final delivery consistency are tracked above; final team integration is not claimed.
