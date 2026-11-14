"""EMIT L2B MIN (Earth): the zones to read, and the conversion of one granule into pixel counts per H3 cell.

Counts are stored, not means: adding the counts of two granules gives exactly the same result as
processing them together, so Earth can be processed granule by granule.
"""

from __future__ import annotations

from typing import NamedTuple

import h3
import numpy as np
import pandas as pd
import xarray as xr

from families import ALL_FAMILIES, MINERAL_FAMILIES, emit_lookup_table

VARIABLES = ["group_1_mineral_id", "group_2_mineral_id"]
COUNT_COLUMNS = ["n_mesures", "n_detecte", *[f"n_{f}" for f in ALL_FAMILIES], "n_granules"]


class Zone(NamedTuple):
    name: str
    west: float
    south: float
    east: float
    north: float
    max_granules: int | None = None     # overrides --emit-max for this zone


# Known Earth analogues where EMIT is read at full resolution (60 m). Add a line for a new zone.
EMIT_ZONES = [
    # Hyperarid soils and salts, Mars analogue
    Zone("atacama", -70.5, -25.5, -68.5, -23.5),
    # Death Valley and Mojave: evaporites, alluvial fans
    Zone("death_valley", -117.5, 35.5, -115.5, 37.0),
    # Rio Tinto mines and upper river: acidic iron sulfates and oxides (jarosite), Meridiani analogue.
    # Small and often cloudy target: more scenes, the least cloudy ones.
    Zone("rio_tinto", -6.75, 37.55, -6.45, 37.80, 40),
    # Lower Rio Tinto and Iberian Pyrite Belt (Tharsis)
    Zone("rio_tinto_aval", -7.0, 37.2, -6.4, 37.6),
    # Hanksville and San Rafael Swell (Mars Desert Research Station): clays, sandstones
    Zone("utah_mdrs", -111.3, 38.0, -110.3, 39.0),
    # Archean basalts and cherts
    Zone("pilbara", 118.5, -22.0, 120.5, -20.5),
    # Sand, gypsum
    Zone("namib", 14.5, -25.5, 16.0, -23.5),
    # Saharan basalts and volcanoes
    Zone("hoggar", 5.0, 22.5, 6.5, 23.8),
    # Weathered basalts and tephra, lunar and Martian analogue
    Zone("mauna_kea", -156.0, 19.3, -155.0, 20.1),
    # Qaidam Basin: evaporites and yardangs, Mars analogue
    Zone("qaidam", 92.0, 37.5, 94.0, 38.5),
    # Recent basaltic lava flows
    Zone("lanzarote", -14.0, 28.8, -13.4, 29.3),
    # Danakil Depression (Dallol): salts, sulfates, hydrothermal activity
    Zone("danakil", 40.0, 14.0, 40.6, 14.5),
    # El Pinacate: basaltic volcanic field and maars
    Zone("pinacate", -114.0, 31.6, -113.2, 32.1),
    # Gypsum dunes, analogue of the sulfate dunes of Olympia Undae
    Zone("white_sands", -106.6, 32.6, -106.1, 33.1),
    # Acid saline lakes of Western Australia: jarosite, Meridiani analogue (Benison and Bowen 2006)
    Zone("lacs_acides_australie", 121.0, -33.0, 122.0, -32.3),
    # Salt crust, analogue of the Martian chloride deposits
    Zone("salar_uyuni", -68.2, -20.6, -67.0, -19.8),
    # Simple impact crater and its ejecta
    Zone("meteor_crater", -111.2, 34.9, -110.9, 35.15),
    # Impact crater in the Deccan basalts, Martian crater analogue
    Zone("lonar", 76.4, 19.9, 76.6, 20.05),
    # Sandstones and rocky desert, Martian terrain analogue
    Zone("wadi_rum", 35.2, 29.4, 35.7, 29.8),
]


def netcdf_engine() -> str:
    """h5netcdf when it is installed together with h5py, otherwise netCDF4: both read the EMIT groups."""
    try:
        import h5netcdf  # noqa: F401
        import h5py  # noqa: F401
        return "h5netcdf"
    except ImportError:
        return "netcdf4"


def _read(path, engine: str) -> dict:
    with xr.open_dataset(path, engine=engine) as ds:
        d = {v: ds[v].values for v in VARIABLES}
    with xr.open_dataset(path, engine=engine, group="location", mask_and_scale=False) as loc:
        d["lat"] = loc["lat"].values
        d["lon"] = loc["lon"].values
    return d


def read_granule(path) -> dict:
    """Mineral variables and latitude/longitude of every pixel (sensor geometry)."""
    engine = netcdf_engine()
    try:
        return _read(path, engine)
    except (ImportError, ValueError) as e:
        if engine == "netcdf4":
            raise
        print(f"    h5netcdf unavailable ({e}): reading with netCDF4")
        return _read(path, "netcdf4")


def granule_counts(path, resolution: int = 5, step: int = 1) -> pd.DataFrame:
    """One EMIT granule -> one row per H3 cell it touches, with the columns of COUNT_COLUMNS:
    n_mesures (measured pixels), n_detecte (pixels with at least one recognized mineral),
    n_<family> (pixels where the family is recognized, group 1 or 2) and n_granules.

    step: keep only one pixel in `step` along each direction (faster, for tests).
    """
    lut = emit_lookup_table()
    d = read_granule(path)
    s = (slice(None, None, step), slice(None, None, step))
    lat, lon = d["lat"][s], d["lon"][s]
    ids1, ids2 = d["group_1_mineral_id"][s], d["group_2_mineral_id"][s]

    # -9999 = no geolocation
    measured = np.isfinite(ids1) & np.isfinite(ids2) & (np.abs(lat) <= 90) & (np.abs(lon) <= 180)
    lat, lon = lat[measured], lon[measured]
    if lat.size == 0:
        return pd.DataFrame(columns=["h3", *COUNT_COLUMNS])

    def family_ranks(ids):
        ids = np.nan_to_num(ids[measured], nan=0).astype(np.int64)
        known = (ids > 0) & (ids < len(lut))
        rank = np.full(ids.shape, -1, dtype=np.int16)
        rank[known] = lut[ids[known]]
        return rank

    r1, r2 = family_ranks(ids1), family_ranks(ids2)
    columns = {"h3": [h3.latlng_to_cell(a, b, resolution) for a, b in zip(lat.tolist(), lon.tolist())],
               "n_mesures": np.ones(lat.size, dtype=np.int32)}
    mineral = np.zeros(lat.size, dtype=bool)
    for i, family in enumerate(ALL_FAMILIES):
        present = (r1 == i) | (r2 == i)
        columns[f"n_{family}"] = present
        if family in MINERAL_FAMILIES:
            mineral |= present
    columns["n_detecte"] = mineral

    counts = pd.DataFrame(columns).groupby("h3", sort=False).sum().astype(np.int64).reset_index()
    counts["n_granules"] = 1
    return counts[["h3", *COUNT_COLUMNS]]


def merge_counts(tables) -> pd.DataFrame:
    """Add up count tables (several granules)."""
    tables = [t for t in tables if len(t)]
    if not tables:
        return pd.DataFrame(columns=["h3", *COUNT_COLUMNS])
    return pd.concat(tables, ignore_index=True).groupby("h3", sort=False)[COUNT_COLUMNS].sum().reset_index()
