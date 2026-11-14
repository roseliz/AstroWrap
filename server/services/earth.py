"""The Earth in memory: every land cell and the variables of each module, as float32.

~600,000 cells × ~60 columns: about 150 MB. Read once at startup (in the background), then shared by every
search. Mars and the Moon are never loaded whole: only the cells of the reference area are read, at each search.
"""

import threading
import time
from dataclasses import dataclass, field

import h3
import numpy as np

from . import db, impact
from .scoring.registry import MODULES


def to_ints(cells) -> np.ndarray:
    return np.fromiter((h3.str_to_int(c) for c in cells), dtype=np.uint64, count=len(cells))


@dataclass
class Earth:
    cells: np.ndarray                                    # sorted uint64
    modules: dict = field(default_factory=dict)          # key -> EarthData
    filters: dict = field(default_factory=dict)          # vegetation, urban, protected: float32 (n,)
    impact: dict = field(default_factory=dict)           # protected, strict, airport_km, mines (services/impact.py)
    impact_sources: dict = field(default_factory=dict)
    region_parents: np.ndarray = None                    # resolution-3 cell of each cell (funnel animation)
    region_order: np.ndarray = None                      # cells sorted by region
    load_s: float = 0.0

    def h3(self, i) -> str:
        return h3.int_to_str(int(self.cells[i]))

    def index(self, cell: str):
        c = np.uint64(h3.str_to_int(cell))
        i = int(np.searchsorted(self.cells, c))
        return i if i < len(self.cells) and self.cells[i] == c else None


_earth = None
_error = None
_ready = threading.Event()
_lock = threading.Lock()


def load() -> Earth:
    t0 = time.time()
    files = sorted({str(m.path(t, "earth")) for m in MODULES for t in m._tables() if m.path(t, "earth").is_file()})
    if not files:
        raise FileNotFoundError(f"no module results for the Earth in {db.config.DATA_DIR}")
    d = db.cursor().execute("SELECT DISTINCT h3 FROM read_parquet(?, union_by_name = true)", [files]).fetchnumpy()
    T = Earth(np.sort(to_ints(d["h3"])))
    for m in MODULES:
        D = m.load_earth(T.cells, to_ints)
        if D is not None:
            T.modules[m.key] = D
    f = db.parquet_path("geology_mineralogy", "geology_mineralogy", "earth")
    if f.is_file():
        data = db.read(f, ["part_vegetation", "part_artificiel"])
        pos = np.searchsorted(T.cells, to_ints(data["h3"]))
        for k, col in (("vegetation", "part_vegetation"), ("urban", "part_artificiel")):
            x = np.full(len(T.cells), np.nan, dtype=np.float32)
            x[pos] = data[col]
            T.filters[k] = x
    impact.load(T, to_ints)
    if "protected" in T.impact:
        T.filters["protected"] = T.impact["protected"]
    T.region_parents = np.fromiter((h3.str_to_int(h3.cell_to_parent(h3.int_to_str(int(c)), 3)) for c in T.cells),
                                   dtype=np.uint64, count=len(T.cells))
    T.region_order = np.argsort(T.region_parents, kind="stable")
    T.load_s = round(time.time() - t0, 1)
    print(f"  Earth: {len(T.cells):,} cells, modules {', '.join(T.modules)} ({T.load_s} s)", flush=True)
    return T


def start():
    """Reads the Earth in the background when the server starts."""
    def run():
        global _earth, _error
        try:
            with _lock:
                if _earth is None:          # a search may already have loaded it
                    _earth = load()
        except Exception as e:          # noqa: BLE001: reported by /api/health and by every search
            _error = e
            print(f"  Earth data unreadable: {e}", flush=True)
        finally:
            _ready.set()
    threading.Thread(target=run, daemon=True).start()


def earth(wait_s: float = 300) -> Earth:
    global _earth
    if _earth is None and not _ready.is_set() and not _lock.locked():
        with _lock:
            if _earth is None:
                _earth = load()
                _ready.set()
    _ready.wait(wait_s)
    if _earth is None:
        raise FileNotFoundError(str(_error) if _error else "the Earth data are not loaded yet")
    return _earth


def status() -> dict:
    if _earth is not None:
        return {"ready": True, "earth_cells": int(len(_earth.cells)), "modules": list(_earth.modules),
                "load_s": _earth.load_s, "impact": sorted(_earth.impact)}
    return {"ready": False, "error": str(_error) if _error else None}
