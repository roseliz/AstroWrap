"""One EMIT granule (MIN, MINUNCERT and L2A mask files) -> two small count tables per H3 cell.

Thresholds are not applied here. Pixels are counted per quality class (fit score `fit`, band depth /
uncertainty ratio `snr`, weight of the family in the library entry, mask state), so thresholds can be
chosen afterwards on these counts without reading the files again, and the counts of several granules
add up.

Table `cellules`: granule, version, h3, drap, n (geolocated pixels per combination of mask flags).
Table `histo`:    granule, version, h3, famille, drap, wbin, fitbin, snrbin, n (detected pixels),
                  bd (sum of the band depths).
`drap` is a bit field (FLAGS), so the mask is chosen afterwards. The classic cloud mask (brightness
threshold) flags very bright surfaces (White Sands gypsum dunes: 100 % "cloud" under a clear sky);
SpecTf (spectral model) does not, or much less.
A pixel counts at most once per family (groups 1 and 2 together: the best detection is kept). Everything
is vectorized (numpy, and DuckDB with the h3 extension): no Python loop per pixel.
"""

from __future__ import annotations

import time
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

from families import FAMILIES, weight_matrix
from utils import duckdb_h3

FIT_BINS = np.round(np.arange(0, 1.0001, 0.05), 2)                       # fitbin k: fit in [0.05 k, 0.05 (k+1))
SNR_BINS = np.array([0, 1, 2, 3, 4, 5, 7, 10, 15, 20, 30, 50], float)   # snrbin k: snr >= SNR_BINS[k]
WEIGHT_BINS = np.array([0.1, 0.25, 0.5], float)                          # wbin k: weight >= WEIGHT_BINS[k]
# Bits of the `drap` field (L2A mask band name, lower case -> bit)
FLAGS = {"cloud flag": 1, "dilated cloud flag": 2, "spectf-cloud flag": 4, "cirrus flag": 8,
         "water flag": 16, "spacecraft flag": 32}
# Possible masks: bits that make a pixel invalid (phase 1 choice: spectf, see thresholds.py)
MASKS = {
    "classic": FLAGS["cloud flag"] | FLAGS["cirrus flag"] | FLAGS["water flag"] | FLAGS["spacecraft flag"],
    "classic_dilated": FLAGS["cloud flag"] | FLAGS["dilated cloud flag"] | FLAGS["cirrus flag"]
                       | FLAGS["water flag"] | FLAGS["spacecraft flag"],
    "spectf": FLAGS["spectf-cloud flag"] | FLAGS["cirrus flag"] | FLAGS["water flag"] | FLAGS["spacecraft flag"],
    "cirrus_water": FLAGS["cirrus flag"] | FLAGS["water flag"] | FLAGS["spacecraft flag"],
}


def _mask_band_names(h) -> list[str]:
    return [(x.decode() if isinstance(x, bytes) else str(x)).strip().lower()
            for x in h["sensor_band_parameters/mask_bands"][:]]


def read_granule(f_min, f_unc, f_mask) -> dict:
    """Read the variables used. f_*: local paths or file objects (h5py accepts both)."""
    d = {}
    with h5py.File(f_min, "r") as h:
        for g in (1, 2):
            d[f"id{g}"] = h[f"group_{g}_mineral_id"][:]
            d[f"bd{g}"] = h[f"group_{g}_band_depth"][:]
        d["lat"], d["lon"] = h["location/lat"][:], h["location/lon"][:]
    with h5py.File(f_unc, "r") as h:
        for g in (1, 2):
            d[f"fit{g}"] = h[f"group_{g}_fit"][:]
            d[f"unc{g}"] = h[f"group_{g}_band_depth_unc"][:]
    with h5py.File(f_mask, "r") as h:
        names = _mask_band_names(h)
        m = h["mask"][:]
    flags = np.zeros(m.shape[:2], np.int8)
    for i, name in enumerate(names):
        if name in FLAGS:
            flags |= np.where(m[..., i] > 0.5, FLAGS[name], 0).astype(np.int8)
    d["drap"] = flags
    return d


def _bin(x: np.ndarray, bins: np.ndarray) -> np.ndarray:
    return (np.searchsorted(bins, x, side="right") - 1).astype(np.int8)


def count_tables(d: dict, granule: str, version: str, resolution: int = 5, con=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pixel counts of one granule: the `cellules` and `histo` tables described above."""
    W = weight_matrix()
    geo = (np.abs(d["lat"]) <= 90) & (np.abs(d["lon"]) <= 180) & (d["id1"] != -9999) & (d["id2"] != -9999)
    lat, lon, flags = d["lat"][geo], d["lon"][geo], d["drap"][geo]
    px = pd.DataFrame({"i": np.arange(lat.size, dtype=np.int32), "lat": lat, "lon": lon, "drap": flags})
    # Best detection per family and per pixel: (weight, fit, snr, bd) of the winning group
    best = {}
    for g in (1, 2):
        ids = d[f"id{g}"][geo].astype(np.int64)
        known = (ids > 0) & (ids < W.shape[0])
        w = np.zeros((ids.size, len(FAMILIES)), np.float32)
        w[known] = W[ids[known]]
        bd = d[f"bd{g}"][geo]
        unc = d[f"unc{g}"][geo]
        snr = np.where(unc > 0, bd / np.where(unc > 0, unc, 1), 0).astype(np.float32)
        fit = d[f"fit{g}"][geo]
        for k, f in enumerate(FAMILIES):
            sel = w[:, k] >= WEIGHT_BINS[0]
            candidate = np.where(sel, fit, -1)          # fit = -1: family absent from this group
            previous = best.get(f)
            if previous is None:
                best[f] = (np.where(sel, w[:, k], 0), candidate, snr, bd)
            else:                                        # keep the group with the best fit score
                better = candidate > previous[1]
                best[f] = tuple(np.where(better, a, b) for a, b in zip((w[:, k], candidate, snr, bd), previous))
    rows = []
    for f, (w, fit, snr, bd) in best.items():
        sel = fit >= 0
        if not sel.any():
            continue
        rows.append(pd.DataFrame({
            "i": np.nonzero(sel)[0].astype(np.int32), "famille": f,
            "wbin": _bin(w[sel], WEIGHT_BINS), "fitbin": np.clip(_bin(fit[sel], FIT_BINS), 0, 19),
            "snrbin": _bin(np.nan_to_num(snr[sel], nan=0, posinf=1e6).clip(0), SNR_BINS),
            "bd": bd[sel].astype(np.float32)}))
    c = duckdb_h3(con)
    c.register("px", px)
    # Explicit index: DuckDB does not guarantee the row order of a scanned table (parallel reads)
    c.execute(f"CREATE OR REPLACE TEMP TABLE pxc AS SELECT i, drap, "
              f"h3_h3_to_string(h3_latlng_to_cell(lat, lon, {resolution})) AS h3 FROM px")
    cells = c.execute("SELECT h3, drap, count(*) n FROM pxc GROUP BY ALL").df()
    if rows:
        c.register("det", pd.concat(rows, ignore_index=True))
        histo = c.execute("""SELECT p.h3, d.famille, p.drap, d.wbin, d.fitbin, d.snrbin, count(*) n, sum(d.bd) bd
                             FROM det d JOIN pxc p USING (i) GROUP BY ALL""").df()
    else:
        histo = pd.DataFrame(columns=["h3", "famille", "drap", "wbin", "fitbin", "snrbin", "n", "bd"])
    for t in (cells, histo):
        t.insert(0, "version", version)
        t.insert(0, "granule", granule)
    return cells, histo


def reduce_for_production(cells: pd.DataFrame, histo: pd.DataFrame, invalid_bits: int, min_weight: float = 0.1,
                          min_fit: float = 0.0):
    """Lighter production output: mask applied, weight and fit classes fixed (thresholds.py).
    cells -> granule, version, h3, n_total, n_valides; histo -> granule, version, h3, famille, snrbin, n, bd.
    The snr classes are kept, so the snr thresholds can still change without reading EMIT again."""
    keys = ["granule", "version", "h3"]
    valid = (cells["drap"].astype(int) & invalid_bits) == 0
    c = (cells.assign(n_valides=np.where(valid, cells["n"], 0))
         .groupby(keys, as_index=False).agg(n_total=("n", "sum"), n_valides=("n_valides", "sum")))
    wmin = int(np.searchsorted(WEIGHT_BINS, min_weight))
    fmin = int(np.searchsorted(FIT_BINS, min_fit))
    h = histo[((histo["drap"].astype(int) & invalid_bits) == 0) & (histo["wbin"] >= wmin) & (histo["fitbin"] >= fmin)]
    h = h.groupby([*keys, "famille", "snrbin"], as_index=False)[["n", "bd"]].sum()
    return c, h


def process_local(f_min: Path, f_unc: Path, f_mask: Path, granule: str, version: str, resolution: int = 5):
    """Read one downloaded granule and return its count tables and timings."""
    t0 = time.time()
    d = read_granule(f_min, f_unc, f_mask)
    t1 = time.time()
    c, h = count_tables(d, granule, version, resolution)
    return c, h, {"s_lecture": t1 - t0, "s_calcul": time.time() - t1}
