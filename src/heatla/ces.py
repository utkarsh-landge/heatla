"""CalEnviroScreen tract -> ZIP aggregation that handles missing values correctly.

CalEnviroScreen GIS layers store -999 where a tract has no value for an indicator.
That number is a marker, not a measurement. If it is averaged with real values, a
single affected tract can push a ZIP-level mean far below zero.

The rule implemented here:
  1. -999 (and blank / None / NaN) means "missing" for that indicator in that tract.
  2. A tract contributes to a ZIP's mean for an indicator only if it has a value for
     that indicator AND a positive population. A missing value is left out of the
     numerator and its population is left out of the denominator.
  3. If no tract in a ZIP has a value for an indicator, the ZIP value is None
     (written as an empty cell). Nothing is filled in.

Pure standard library, so the fetch scripts can import it without extra dependencies.
"""
from __future__ import annotations

import math
from typing import Iterable, Mapping

SENTINEL = -999.0


def to_value(v) -> float | None:
    """Parse one raw cell; return None for blank, None, NaN or the -999 sentinel."""
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        if v == "" or v.lower() in ("none", "nan", "na", "null"):
            return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or x == SENTINEL:
        return None
    return x


def to_raw_number(v) -> float | None:
    """Parse one raw cell WITHOUT treating -999 as missing (reproduces the old behaviour)."""
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def weighted_mean(pairs: Iterable[tuple[float | None, float | None]],
                  ndigits: int | None = 4) -> float | None:
    """Population-weighted mean of (value, weight) pairs.

    Pairs with a missing value, or a missing / non-positive weight, are skipped
    entirely: neither the value nor its weight is used. Returns None if nothing is left.
    """
    num = den = 0.0
    for value, weight in pairs:
        if value is None or weight is None or weight <= 0:
            continue
        num += value * weight
        den += weight
    if den <= 0:
        return None
    out = num / den
    return round(out, ndigits) if ndigits is not None else out


def zip_key(v) -> str | None:
    """Normalise a ZIP cell (90001, '90001', 90001.0) to a 5-character string."""
    x = to_raw_number(v)
    if x is None:
        return None
    return str(int(x)).zfill(5)


def aggregate_tracts(rows: Iterable[Mapping], field_map: Mapping[str, str],
                     zip_field: str = "ZIP", weight_field: str = "TotPop19",
                     treat_sentinel_as_missing: bool = True,
                     ndigits: int = 4) -> dict[str, dict]:
    """Aggregate tract rows to one record per ZIP.

    field_map maps raw tract field -> output name. Each output record has:
      zip, pop (sum of tract populations), n_tracts,
      <name> (weighted mean or None), n_used__<name>, n_missing__<name>
    Set treat_sentinel_as_missing=False only to reproduce the old, incorrect values.
    """
    parse = to_value if treat_sentinel_as_missing else to_raw_number
    groups: dict[str, list[Mapping]] = {}
    for r in rows:
        z = zip_key(r.get(zip_field))
        if z is not None:
            groups.setdefault(z, []).append(r)

    out: dict[str, dict] = {}
    for z, recs in groups.items():
        weights = [to_raw_number(r.get(weight_field)) for r in recs]
        rec = {"zip": z, "pop": sum(w for w in weights if w), "n_tracts": len(recs)}
        for raw, name in field_map.items():
            vals = [parse(r.get(raw)) for r in recs]
            used = [(v, w) for v, w in zip(vals, weights)
                    if v is not None and w is not None and w > 0]
            rec[name] = weighted_mean(used, ndigits)
            rec[f"n_used__{name}"] = len(used)
            rec[f"n_missing__{name}"] = sum(1 for r in recs if to_value(r.get(raw)) is None)
        out[z] = rec
    return out


def _self_check() -> None:
    """Tiny worked example; raises AssertionError if the rule above is broken."""
    rows = [{"ZIP": 90001, "TotPop19": 1000, "Unempl": 10.0},
            {"ZIP": 90001, "TotPop19": 3000, "Unempl": -999},     # missing: skip value + weight
            {"ZIP": 90001, "TotPop19": 1000, "Unempl": 20.0},
            {"ZIP": 90002, "TotPop19": 500, "Unempl": -999},      # nothing valid -> None
            {"ZIP": 90003, "TotPop19": 0, "Unempl": 7.0}]         # no population -> None
    good = aggregate_tracts(rows, {"Unempl": "unemployment_pct"})
    assert good["90001"]["unemployment_pct"] == 15.0, good["90001"]
    assert good["90001"]["n_used__unemployment_pct"] == 2
    assert good["90001"]["n_missing__unemployment_pct"] == 1
    assert good["90002"]["unemployment_pct"] is None
    assert good["90003"]["unemployment_pct"] is None
    old = aggregate_tracts(rows, {"Unempl": "unemployment_pct"}, treat_sentinel_as_missing=False)
    assert old["90001"]["unemployment_pct"] == -593.4, old["90001"]   # the bug being fixed
    assert to_value("-999") is None and to_value("") is None and to_value("0") == 0.0


if __name__ == "__main__":
    _self_check()
    print("heatla.ces self-check passed")
