"""Impact of a field test campaign on an Earth site: protected areas, land already transformed, access.

This is not a similarity criterion: it is what testing on the site would cost the Earth. The values come from
three preprocessing modules:
- environmental_impact: part_protegee, part_protegee_stricte (WDPA), distance_aeroport_km (OurAirports);
- astrobiology_habitability_caves: part_mine (Maus et al. 2022);
- geology_mineralogy: part_artificiel (already in Earth.filters).
Without the environmental_impact module nothing breaks: the search just returns no "impact" block.

WDPA terms of use: only derived values are shown, never downloadable, with the citation and the version
(citation()). The WDPA itself is never on the server.
"""

import json

import numpy as np

from . import db

FOLDER = "environmental_impact"
COLUMNS = {"protected": "part_protegee", "strict": "part_protegee_stricte", "airport_km": "distance_aeroport_km"}
MONTHS = {"Jan": "January", "Feb": "February", "Mar": "March", "Apr": "April", "May": "May", "Jun": "June",
          "Jul": "July", "Aug": "August", "Sep": "September", "Oct": "October", "Nov": "November", "Dec": "December"}
AVERAGED = ("protected", "strict", "mines")     # averaged over the site's footprint; the airport: the center's


def parquet_file():
    return db.parquet_path(FOLDER, FOLDER, "earth")


def _align(cells: np.ndarray, to_ints, data: dict, col: str) -> np.ndarray:
    """Column read from a file, aligned on the Earth cells (NaN for the cells the file does not have)."""
    x = np.full(len(cells), np.nan, dtype=np.float32)
    e = to_ints(data["h3"])
    pos = np.minimum(np.searchsorted(cells, e), len(cells) - 1)
    ok = cells[pos] == e
    x[pos[ok]] = data[col][ok]
    return x


def load(T, to_ints) -> None:
    """T.impact: {protected, strict, airport_km, mines} as float32 aligned on T.cells; T.impact_sources."""
    T.impact, T.impact_sources = {}, {}
    f = parquet_file()
    if f.is_file():
        present = set(db.columns(f))
        data = db.read(f, [c for c in COLUMNS.values() if c in present])
        for k, col in COLUMNS.items():
            if col in data and np.isfinite(data[col]).any():
                T.impact[k] = _align(T.cells, to_ints, data, col)
        T.impact_sources = sources(f)
    if not T.impact:
        return
    f = db.parquet_path("astrobiology_habitability_caves", "astrobiology_habitability_caves", "earth")
    if f.is_file() and "part_mine" in db.columns(f):
        T.impact["mines"] = _align(T.cells, to_ints, db.read(f, ["part_mine"]), "part_mine")


def sources(f) -> dict:
    """"sources" metadata written by the module (WDPA citation, version)."""
    try:
        for k, v in db.cursor().execute("SELECT key, value FROM parquet_kv_metadata(?)", [str(f)]).fetchall():
            if bytes(k) == b"sources":
                return json.loads(bytes(v).decode("utf-8"))
    except Exception:              # noqa: BLE001: missing or unreadable metadata, the citation stays generic
        pass
    return {}


def citation(impact_sources: dict) -> str:
    """Citation required by UNEP-WCMC, with the month and year of the version used."""
    v = (impact_sources or {}).get("wdpa_version") or ""
    month, year = (MONTHS.get(v[:3], v[:3]), v[-4:]) if len(v) >= 7 else ("", "")
    when = f"{month} {year}" if year else "[version]"
    return (f"UNEP-WCMC and IUCN ({year or 'year'}), Protected Planet: The World Database on Protected Areas (WDPA), "
            f"{when}, Cambridge, UK: UNEP-WCMC and IUCN. www.protectedplanet.net")


def extras(T) -> dict:
    """Columns to average over the footprint of each site (footprint.similarities)."""
    return {c: T.impact[c] for c in AVERAGED if c in getattr(T, "impact", {})}


def public(T, rows, means: dict, rounding) -> dict:
    """"impact" block of the pool: shares averaged over the footprint, airport distance from the center."""
    if not getattr(T, "impact", None):
        return None
    out = {c: rounding(means[c], 4 if c == "mines" else 3) for c in AVERAGED if c in means}
    if "airport_km" in T.impact:
        out["airport_km"] = rounding(T.impact["airport_km"][np.asarray(rows, dtype=np.int64)], 0)
    out["source"] = citation(T.impact_sources) if "protected" in T.impact else None
    return out
