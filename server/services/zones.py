"""Reference area: H3 cells from the interface (resolution 6, compacted or not) -> resolution-5 cells."""

import hashlib
import json

import h3
import numpy as np

from ..core import config


def to_resolution(cells: list):
    """(sorted resolution-5 cells, number of resolution-6 tiles of the area in each of them)."""
    res = config.RESOLUTION
    tiles = 0
    counts = {}
    for c in cells:
        if not h3.is_valid_cell(c):
            raise ValueError(f"invalid H3 cell: {c}")
        r = h3.get_resolution(c)
        tiles += 7 ** max(0, 6 - r)
        if tiles > config.MAX_ZONE_CELLS:
            raise ValueError(f"area too large: more than {config.MAX_ZONE_CELLS} tiles at resolution 6")
        if r <= res:
            for e in (h3.cell_to_children(c, res) if r < res else [c]):
                counts[e] = counts.get(e, 0.0) + 7.0 ** (6 - res)
        else:
            p = h3.cell_to_parent(c, res)
            counts[p] = counts.get(p, 0.0) + 7.0 ** max(0, 6 - r)
    if not counts:
        raise ValueError("empty area")
    keys = sorted(counts)
    return keys, np.array([counts[c] for c in keys])


# ------------------------------------------------------------------ saved areas
# The interface does not put the cells in the page address: "Compare with the Earth" saves the area here and opens
# index.html#mars/<id>. Same area, same id; JSON files in cache/zones/ (a few KB each).
_ZONES = {}


def _folder():
    d = config.CACHE_DIR / "zones"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(body: str, cells: list) -> str:
    """Validates the area and returns a short identifier (12 hexadecimal characters)."""
    cells = sorted(set(cells))
    to_resolution(cells)        # same validation as the search (valid cells, maximum size)
    ident = hashlib.sha256(f"{body}:{','.join(cells)}".encode()).hexdigest()[:12]
    if ident not in _ZONES:
        _ZONES[ident] = {"body": body, "h3_cells": cells}
        try:
            (_folder() / f"{ident}.json").write_text(json.dumps(_ZONES[ident]), encoding="utf-8")
        except OSError:
            pass                # no disk: the area stays in memory until the server stops
    return ident


def load(ident: str):
    if ident not in _ZONES:
        f = config.CACHE_DIR / "zones" / f"{ident}.json"
        if not f.is_file():
            return None
        _ZONES[ident] = json.loads(f.read_text(encoding="utf-8"))
    return _ZONES[ident]


# ------------------------------------------------------------------ terrain of an area (landing-site mission)
FLAT_THRESHOLD = 0.5    # a cell where less than half of the ground is under 5° of slope is too rough to land


def terrain(body: str, cells: list) -> dict:
    """Flat ground share (slope < 5°, 500 m base of the topography_morphometry module) of each resolution-5 cell
    of the area, and its mean over the area (weighted by the painted tiles). Cells without data: left out of
    `cells`."""
    from . import db
    keys, weights = to_resolution(cells)
    f = db.parquet_path("topography_morphometry", "topography_morphometry", body, "_b500")
    if not f.is_file():
        return {"cells": {}, "flat": None, "threshold": FLAT_THRESHOLD}
    d = db.read(f, ["part_pente_inf_5"], keys)
    shares = {str(c): float(v) for c, v in zip(d["h3"], d["part_pente_inf_5"]) if np.isfinite(v)}
    w = np.array([weights[i] for i, c in enumerate(keys) if c in shares])
    x = np.array([shares[c] for c in keys if c in shares])
    return {"cells": {c: round(v, 3) for c, v in shares.items()},
            "flat": round(float((w * x).sum() / w.sum()), 3) if len(x) else None, "threshold": FLAT_THRESHOLD}
