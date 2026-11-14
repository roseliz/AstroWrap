"""Comparing an area with an area: each candidate Earth site is judged over a surface as large as the reference
area (a disk of H3 cells around it), not over its single cell.

Why: the area painted on Mars is often thousands of km², a resolution-5 cell is ~250 km². Judging the cell alone
keeps sites whose surroundings (sea, neighboring valley...) look like nothing.

How, for the cells of the pool sent to the browser (~20,000, in chunks):
1. footprint = disk of k rings around the cell, k chosen to cover about the same area in km² as the reference
   area (3k² + 3k + 1 cells; k ≤ K_MAX). Careful: an H3 cell covers the same angle on every body, hence an area
   (R_body / R_Earth)² times smaller on Mars (0.28) and on the Moon (0.074);
2. each module variable is averaged over the cells of the footprint (just as the reference is the mean of the
   area's cells), then compared with the reference using the same rules (scoring/base.py);
3. water share = share of the footprint cells missing from the Earth data (sea, large lakes); the interface
   discards sites above MAX_WATER.
"""

import concurrent.futures as cf
import math
from dataclasses import replace

import h3
import h3.api.basic_int as h3i
import numpy as np

K_MAX = 8                # 217 cells, ~55,000 km²: beyond that, the footprint stays smaller than the area
MAX_WATER = 0.15         # water share tolerated in the footprint (applied by the interface)
CHUNK = 2000             # cells processed at once (memory: CHUNK × cells × columns)
R5_AREA_KM2 = 252.9      # mean area of a resolution-5 cell on the Earth
RADIUS_KM = {"earth": 6371.0088, "mars": 3389.5, "moon": 1737.4}


def zone_area_km2(r6_tiles: float, body: str) -> float:
    """True area of the reference area on its body (7 resolution-6 tiles per resolution-5 cell)."""
    return r6_tiles / 7.0 * R5_AREA_KM2 * (RADIUS_KM[body] / RADIUS_KM["earth"]) ** 2


def rings(r6_tiles: float, body: str) -> int:
    """k such that a disk of k rings on the Earth has the area closest to that of the reference area (ratio)."""
    n = max(1e-6, zone_area_km2(r6_tiles, body) / R5_AREA_KM2)    # equivalent number of Earth cells
    return min(range(K_MAX + 1), key=lambda k: abs(math.log((3 * k * k + 3 * k + 1) / n)))


def footprint_cells(cell: str, k: int) -> list:
    return sorted(h3.grid_disk(cell, k))


def neighbors(T, rows, k: int) -> np.ndarray:
    """(m, 3k²+3k+1): indices of the footprint cells in T.cells, -1 outside the data (water)."""
    K = 3 * k * k + 3 * k + 1
    rows = np.asarray(rows, dtype=np.int64)
    out = np.full((len(rows), K), -1, dtype=np.int64)
    if k == 0:
        out[:, 0] = rows
        return out
    for j, i in enumerate(rows):
        disk = np.array(h3i.grid_disk(int(T.cells[i]), k), dtype=np.uint64)
        pos = np.minimum(np.searchsorted(T.cells, disk), len(T.cells) - 1)
        p = np.where(T.cells[pos] == disk, pos, -1)
        out[j, :len(p)] = p[:K]
    # near the 12 pentagons (at sea), the disk has one cell less: negligible
    return out


def water_share(idx: np.ndarray, k: int) -> np.ndarray:
    K = 3 * k * k + 3 * k + 1
    return ((idx < 0).sum(axis=1) / K).astype(np.float32)


def _mean(x: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """Mean of x (n,) or (n, c) over the cells of each footprint, ignoring water and NaN."""
    valid = idx >= 0
    g = x[np.where(valid, idx, 0)]
    ok = np.isfinite(g) & (valid[:, :, None] if g.ndim == 3 else valid)
    total = np.where(ok, g, 0).sum(axis=1, dtype=np.float32)
    count = ok.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(count > 0, total / np.maximum(count, 1), np.nan).astype(np.float32)


def footprint_data(D, idx: np.ndarray):
    """Copy of EarthData (scoring/base.py) where each row is the mean of a footprint; same scales."""
    return replace(D, values={c: _mean(x, idx) for c, x in D.values.items()},
                   reliability=_mean(D.reliability, idx), raw={})


def similarities(T, refs: dict, keys, rows, k: int, extras=None):
    """({module: similarity (m,)}, {module: reliability (m,)}, water share (m,), {name: mean (m,)}) of the
    footprints of the given rows; extras: other per-Earth-cell columns to average over the footprint (impact.py)."""
    extras = extras or {}
    from .scoring.registry import BY_KEY
    rows = np.asarray(rows, dtype=np.int64)
    sims = {c: np.full(len(rows), np.nan, dtype=np.float32) for c in keys}
    rel = {c: np.full(len(rows), np.nan, dtype=np.float32) for c in keys}
    water = np.zeros(len(rows), dtype=np.float32)
    means = {c: np.full(len(rows), np.nan, dtype=np.float32) for c in extras}

    def chunk(a):
        idx = neighbors(T, rows[a:a + CHUNK], k)
        water[a:a + CHUNK] = water_share(idx, k)
        for c in keys:
            Dz = footprint_data(T.modules[c], idx)
            sims[c][a:a + CHUNK] = BY_KEY[c].score(refs[c], Dz)
            rel[c][a:a + CHUNK] = Dz.reliability
        for c, x in extras.items():
            means[c][a:a + CHUNK] = _mean(x, idx)

    with cf.ThreadPoolExecutor(4) as pool:          # numpy releases the GIL during the means
        list(pool.map(chunk, range(0, len(rows), CHUNK)))
    return sims, rel, water, means
