"""Server settings. Each value can be overridden with an ANALOGUES_<NAME> environment variable."""

import os
from pathlib import Path


def _env(name, default, type_=str):
    v = os.environ.get(f"ANALOGUES_{name}")
    return type_(v) if v not in (None, "") else default


ROOT = Path(__file__).resolve().parents[2]                          # repository root
DATA_DIR = Path(_env("DATA", str(ROOT / "pretreatment_data")))      # module results (Parquet)
RESOLUTION = 5                                                      # H3 resolution of every module
CACHE_DIR = Path(_env("CACHE", str(Path(__file__).resolve().parents[1] / "cache")))   # place names, areas, 3D terrain

# Memory (target: 1 GB for the whole server)
DUCKDB_MEMORY = _env("DUCKDB_MEMORY", "300MB")
DUCKDB_THREADS = _env("DUCKDB_THREADS", 2, int)
DUCKDB_TEMP = _env("DUCKDB_TEMP", "")                               # spill directory (SSD), empty = default

# Reference area
MAX_ZONE_CELLS = _env("MAX_ZONE_CELLS", 60000, int)                 # resolution-6 cells (as in the interface)
MIN_ZONE_CELLS = 1

# Response
TOP_K_DEFAULT = 2000
TOP_K_MAX = 5000
POOL_SIZE = _env("POOL_SIZE", 15000, int)          # cells sent so that the browser can re-weight them
POOL_PER_MODULE = _env("POOL_PER_MODULE", 1500, int)
TOP_PER_STEP = 30                                  # best cells shown at each step of the funnel

# Browser: the interface opens with a double click (origin "null"); online, set the site's domain.
CORS_ORIGINS = [o for o in _env("CORS", "*").split(",") if o]

# Weight presets (the server normalizes the weights)
PRESETS = {
    "balanced": {"name": "Balanced", "weights": {}},
    "landing": {"name": "Landing site", "weights": {"topography": 3, "thermal": 1.5, "wind": 1.5,
                                                    "geology": 0.5, "volatiles": 0.5, "astro": 0}},
    "geology": {"name": "Geology", "weights": {"geology": 3, "topography": 1.5, "thermal": 0.5, "wind": 0.5,
                                               "volatiles": 0.5, "astro": 0.5}},
    "astrobiology": {"name": "Astrobiology", "weights": {"volatiles": 2.5, "astro": 2, "geology": 1.5,
                                                         "thermal": 1, "topography": 0.5, "wind": 0.5}},
    "climate": {"name": "Extreme climate", "weights": {"thermal": 3, "wind": 1.5, "volatiles": 1.5, "topography": 0.5,
                                                       "geology": 0.5, "astro": 0}},
}
