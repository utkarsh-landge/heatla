"""Central configuration for HEATLA.

Every path, seed, and tunable lives here so that a run is reproducible from a
single place. Override anything at runtime with environment variables or by
editing config.yaml at the repo root.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

# --- geography ---------------------------------------------------------------
STATE_FIPS = "06"
COUNTY_FIPS = "037"  # Los Angeles County
COUNTY_GEOID_PREFIX = STATE_FIPS + COUNTY_FIPS  # "06037"

# Projected CRS for all distance work. EPSG:3310 (California Albers) is an
# equal-area projection in metres; using lat/lon degrees for distances is the
# classic way to get silently wrong buffers.
CRS_WORK = "EPSG:3310"
CRS_GEO = "EPSG:4326"

SEED = 461  # course number, easy to remember


@dataclass
class Paths:
    root: Path = ROOT
    data: Path = ROOT / "data"
    raw: Path = ROOT / "data" / "raw"
    interim: Path = ROOT / "data" / "interim"
    processed: Path = ROOT / "data" / "processed"
    reports: Path = ROOT / "reports"
    figures: Path = ROOT / "reports" / "figures"
    tables: Path = ROOT / "reports" / "tables"
    dashboard_data: Path = ROOT / "dashboard" / "public" / "data"

    def ensure(self) -> None:
        for p in (self.raw, self.interim, self.processed, self.figures,
                  self.tables, self.dashboard_data):
            p.mkdir(parents=True, exist_ok=True)


@dataclass
class Config:
    # data mode: "mock" builds a synthetic LA-shaped county so Parts B/C run
    # before any real download lands; "real" reads data/raw.
    data_mode: str = "mock"

    # land-surface temperature source. Landsat is the default; ECOSTRESS is the
    # recommended upgrade (finer thermal, night-time passes) but needs advisor
    # sign-off before it becomes primary.
    lst_source: str = "landsat"          # landsat | ecostress

    # Part A / Part C coverage radii, in metres.
    radius_m: int = 2000                 # default 2 km
    radius_grid_m: tuple = (1609, 2000, 3219)   # 1 mi, 2 km, 2 mi

    # Part C budgets.
    k_default: int = 20
    k_grid: tuple = (5, 10, 15, 20, 25, 30, 40, 50)
    k_report: tuple = (10, 20)
    objectives: tuple = ("count", "pop_x_hvi")
    methods: tuple = ("greedy", "ilp")
    ilp_time_limit_s: int = 120
    n_random_draws: int = 200            # random-placement baseline draws

    # Part B.
    n_spatial_folds: int = 5
    hvi_inputs: tuple = ("lst_f", "pct_age65p", "pct_poverty", "pct_no_canopy")

    # existing cooling centres: "permanent" (~12) or "augmented" (~153)
    centers_set: str = "augmented"

    # mock-mode size
    mock_n_tracts: int = 2498
    mock_n_centers_permanent: int = 12
    mock_n_centers_augmented: int = 153

    seed: int = SEED
    paths: Paths = field(default_factory=Paths)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        cfg = cls()
        path = Path(path) if path else ROOT / "config.yaml"
        if path.exists():
            raw = yaml.safe_load(path.read_text()) or {}
            for k, v in raw.items():
                if k == "paths":
                    continue
                if hasattr(cfg, k):
                    cur = getattr(cfg, k)
                    setattr(cfg, k, tuple(v) if isinstance(cur, tuple) else v)
        # env overrides win last; handy for CI and for one-off runs
        if os.environ.get("HEATLA_DATA_MODE"):
            cfg.data_mode = os.environ["HEATLA_DATA_MODE"]
        if os.environ.get("HEATLA_LST_SOURCE"):
            cfg.lst_source = os.environ["HEATLA_LST_SOURCE"]
        cfg.paths.ensure()
        return cfg

    def to_dict(self) -> dict:
        d = asdict(self)
        d["paths"] = {k: str(v) for k, v in d["paths"].items()}
        return d


CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY", "")
