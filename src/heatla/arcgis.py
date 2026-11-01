"""Minimal, dependency-free client for ArcGIS FeatureServer REST queries.

Used to pull the real UCLA Heat Maps layers and other hosted feature services.
Only the Python standard library is required so the raw-data pull has no heavy
install footprint. Every function returns real server responses untouched.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterator

# Public ArcGIS Online org that hosts the UCLA Heat Maps layers (discovered from
# the Experience Builder app config, item 4c158842b5c94857a06c3a85c7aa02de).
UCLA_SERVICES = (
    "https://services7.arcgis.com/2hYXmwteFLemN5bW/arcgis/rest/services"
)


def _get(url: str, params: dict[str, Any], retries: int = 4) -> dict[str, Any]:
    """GET a JSON response from an ArcGIS REST endpoint, with simple retries.

    Raises on persistent failure so callers never silently continue with
    partial or empty data.
    """
    query = urllib.parse.urlencode(params)
    full = f"{url}?{query}"
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": "heatla-fetch"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and data.get("error"):
                raise RuntimeError(f"ArcGIS error: {data['error']}")
            return data
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            last_err = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed after {retries} tries: {full}\n{last_err}")


def layer_metadata(service: str, layer: int = 0, base: str = UCLA_SERVICES) -> dict:
    """Return the layer definition (fields, geometry type, record limits)."""
    return _get(f"{base}/{service}/FeatureServer/{layer}", {"f": "json"})


def count(service: str, where: str, layer: int = 0, base: str = UCLA_SERVICES) -> int:
    """Return the number of features matching ``where``."""
    r = _get(
        f"{base}/{service}/FeatureServer/{layer}/query",
        {"where": where, "returnCountOnly": "true", "f": "json"},
    )
    return int(r["count"])


def query_all(
    service: str,
    where: str = "1=1",
    out_fields: str = "*",
    layer: int = 0,
    base: str = UCLA_SERVICES,
    return_geometry: bool = False,
    page: int = 2000,
) -> list[dict]:
    """Page through every matching feature and return their attribute dicts.

    Paging uses ``resultOffset``/``resultRecordCount`` so results exceeding the
    layer's ``maxRecordCount`` are retrieved in full.
    """
    rows: list[dict] = []
    offset = 0
    while True:
        r = _get(
            f"{base}/{service}/FeatureServer/{layer}/query",
            {
                "where": where,
                "outFields": out_fields,
                "returnGeometry": "true" if return_geometry else "false",
                "resultOffset": offset,
                "resultRecordCount": page,
                "orderByFields": "FID",
                "f": "json",
            },
        )
        feats = r.get("features", [])
        if not feats:
            break
        if return_geometry:
            rows.extend({**f["attributes"], "_geometry": f.get("geometry")} for f in feats)
        else:
            rows.extend(f["attributes"] for f in feats)
        if len(feats) < page and not r.get("exceededTransferLimit"):
            break
        offset += len(feats)
    return rows


def iter_services() -> Iterator[str]:
    """The UCLA layers referenced by the public Experience app (for provenance)."""
    yield from (
        "zip_ER",
        "zip_ER_map",
        "Daily_Excess_ER_ZIPCODE_with_county",
        "calenviroscreen_test3",
        "county_ER",
    )
