## Experimental setup — Part 2

**Question:** Do four additional ACS features improve prediction of UCLA's historical category-4 label within LA County?

| Item | Setup |
|---|---|
| Study area and sample | LA County; 287 unique ZIPs and 287 rows in each configuration. |
| Exclusions | Start with 289 ZIPs; exclude 91123 and 91522 because coordinates are missing. No rows are excluded for missing feature values. |
| Prediction target | UCLA's published category-4 estimated excess ER visits per 10,000 residents, labelled 2008–2018. The target is unchanged; no L4−L3 subtraction is used. |
| Base model | 11 common predictors from the corrected statewide input table. Heat level is fixed at 4 and omitted as a predictor. |
| Augmented model | The same 11 predictors plus renter share, no-vehicle household share, uninsured share and construction-industry employment share: 15 predictors in total. The four additions use ACS 2018 five-year estimates (2014–2018). |
| Validation | Five-fold spatial cross-validation within LA. Reuse the original geographic groups. Train on four groups and test on the remaining group, repeating until every ZIP has one out-of-fold prediction. |
| Controlled conditions | Identical ZIPs, labels, folds, common feature values, model settings and evaluation rules for both configurations. |
| Algorithms | Poisson regression, random forest and gradient boosting; fixed settings, seed 42, no tuning on held-out data. Exact settings are in experiment_config.json. |
| Missing values and scaling | Fit median imputation on each training fold only. For Poisson, also fit standardization on the training fold only. |
| Population | Excluded as a predictor; retained as a Poisson training weight. Evaluation weights ZIPs equally. Median household income is also excluded as a predictor. |
| References | Training-fold mean baseline; CES percentile ranking reference on the same 273 ZIPs with available CES values. CES is not evaluated with ER-rate R². |
| Evaluation metrics | R², RMSE, MAE, Spearman correlation and top-10% recall; supplementary top-20% recall. Report pooled out-of-fold and per-fold results. |

### Fold sizes

| Held-out group | Training ZIPs | Test ZIPs |
|---|---:|---:|
| 0 | 187 | 100 |
| 1 | 230 | 57 |
| 2 | 217 | 70 |
| 3 | 239 | 48 |
| 4 | 275 | 12 |

**Difference from Part 1's whole-LA holdout:** Part 2 trains and tests on separate geographic groups within LA. The whole-LA holdout trains on California ZIPs outside LA and tests on LA. These are different evaluation designs.

**Scope:** This estimates a historical label; it is not a daily heat-wave forecast. ACS 2014–2018 does not cover the full 2008–2018 target period, geographic boundaries have not been harmonized, and the cumulative interpretation of the category-4 label remains unconfirmed. Feature definitions and source periods are in [Unified Feature Comparison](FEATURE_COMPARISON_TABLE.md).
