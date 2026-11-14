"""EMIT L3 ASA v002 (spectral abundances of 10 minerals, 0.5 deg boxes), read locally from the cache.

Grid: the file's GeoTransform (latitude_longitude variable) is used, not the `lat` / `lon` axes. The `lat`
axis is shifted one row (0.5 deg) to the north: with it, the northernmost row with data would cover
52.25 to 52.75 N, while no EMIT granule goes beyond 52.21 N (checked on the CMR catalog, phase 2).

The abundances of the 10 minerals do not sum to 1: the product completes them with "Quartz+Feldspar".
The values are kept as they are (sum of the minerals of each family), without renormalization.
"""

from __future__ import annotations

from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd

from families import FAMILIES, MINERALS
from utils import CACHE_DIR, duckdb_h3, earthdata_login

L3_FILE = CACHE_DIR / "emit_l3" / "EMIT_L3_ASA_002.nc"     # 20 MB, downloaded once
STEP_DEG = 0.5
RESOLUTION_M = 55_000                                     # ~0.5 deg at the equator


def ensure_downloaded(path: Path = L3_FILE) -> Path:
    """Download EMIT L3 ASA v002 (a single file) unless it is already in the module cache."""
    if path.is_file():
        return path
    earthaccess = earthdata_login()
    path.parent.mkdir(parents=True, exist_ok=True)
    g = earthaccess.search_data(short_name="EMITL3ASA", version="002")
    links = [u for x in g for u in x.data_links() if u.endswith(".nc") and "UNC" not in u.upper()]
    session = earthaccess.get_requests_https_session()
    with session.get(links[0], stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(8 * 2**20):
                f.write(chunk)
    return path


def read_l3(path: Path = L3_FILE) -> dict:
    """Abundance per family (2D arrays, NaN = no measurement) and box centers from the GeoTransform."""
    with netCDF4.Dataset(ensure_downloaded(path)) as d:
        d.set_auto_mask(False)
        west, dx, _, north, _, dy = [float(x) for x in d["latitude_longitude"].GeoTransform.split()]
        ny, nx = d["Calcite"].shape
        lat = north + dy * (np.arange(ny) + 0.5)
        lon = west + dx * (np.arange(nx) + 0.5)
        abundance = {}
        for f in FAMILIES:
            total = np.zeros((ny, nx))
            measured = np.zeros((ny, nx), bool)
            for m in MINERALS[f]:
                a = d[m][:].astype(float)
                ok = np.isfinite(a) & (a > -9000)
                total += np.where(ok, a, 0)
                measured |= ok
            abundance[f] = np.where(measured, total, np.nan)
    return {"lat": lat, "lon": lon, "west": west, "north": north, "dx": dx, "dy": dy, "abundance": abundance}


def measured_boxes(g: dict | None = None) -> pd.DataFrame:
    """Centers of the boxes where at least one family is measured (extent of the EMIT arid zone)."""
    g = g or read_l3()
    ok = np.zeros_like(next(iter(g["abundance"].values())), bool)
    for a in g["abundance"].values():
        ok |= np.isfinite(a)
    i, j = np.where(ok)
    return pd.DataFrame({"la": g["lat"][i], "lo": g["lon"][j]})


def arid_cells(resolution: int = 5, con=None, g: dict | None = None) -> pd.DataFrame:
    """H3 cells (strings) whose center falls in a measured L3 box (DuckDB + h3 extension)."""
    c = duckdb_h3(con)
    c.register("cases_l3", measured_boxes(g))
    h = STEP_DEG / 2
    return c.execute(f"""SELECT DISTINCT h3_h3_to_string(unnest(h3_polygon_wkt_to_cells(
        'POLYGON((' || (lo-{h}) || ' ' || (la-{h}) || ',' || (lo+{h}) || ' ' || (la-{h}) || ',' || (lo+{h}) || ' ' ||
        (la+{h}) || ',' || (lo-{h}) || ' ' || (la+{h}) || ',' || (lo-{h}) || ' ' || (la-{h}) || '))', {resolution}))) AS h3
        FROM cases_l3""").df()


def sample_points(lat: np.ndarray, lon: np.ndarray, g: dict | None = None) -> pd.DataFrame:
    """L3 abundances (ab_l3_<family>) and box identifier (id_case_l3) at points (H3 cell centers)."""
    g = g or read_l3()
    i = np.floor((lat - g["north"]) / g["dy"]).astype(int)
    j = np.floor((lon - g["west"]) / g["dx"]).astype(int)
    ny, nx = g["abundance"][FAMILIES[0]].shape
    inside = (i >= 0) & (i < ny) & (j >= 0) & (j < nx)
    ic, jc = np.clip(i, 0, ny - 1), np.clip(j, 0, nx - 1)
    t = pd.DataFrame({f"ab_l3_{f}": np.where(inside, g["abundance"][f][ic, jc], np.nan) for f in FAMILIES})
    measured = t.notna().any(axis=1)
    t["id_case_l3"] = np.where(measured, [f"{g['lat'][a]:.2f}_{g['lon'][b]:.2f}" for a, b in zip(ic, jc)], None)
    return t
