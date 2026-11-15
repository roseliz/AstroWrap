"""Common interface of the scoring modules: reference(cells, body), then score(reference).

Each module declares its variables; the mechanics are the same for all of them:

- reference() reads, in the Parquet files of the body (Mars or the Moon), only the cells of the area, with DuckDB,
  and averages them weighted by the number of area tiles in each cell;
- score() compares this reference with every Earth cell, kept in memory (float32), and returns a similarity from
  0 to 1 per cell (NaN: no data) and the reliability of the cell (0 to 1).

Distance of a variable, from 0 (identical) to 1 (very different), by type:
- "abs"       raw value, same meaning on the three bodies (flat ground share, ice share...):
              min(|earth − reference| / scale, CAP) / CAP, scale = standard deviation over the Earth;
- "rank"      rank within its own body (0 = lowest, 1 = highest), same formula: for quantities whose order of
              magnitude changes from one body to another (elevation range, craters, relative wind);
- "deciles"   distribution by deciles (slopes): mean distance of the deciles, same formula;
- "hellinger" shares that sum to 1 (rocks, minerals): Hellinger distance, over the classes the reference measures
              plus a "rest" class (1 − sum), so that two families measured on Mars are not renormalized as if they
              were the whole rock. Classes almost absent from the Earth data (present in fewer than
              PRESENT_SHARE of the measured cells) are removed on both sides: "impact" (GLiM has none), pyroxene
              and olivine (EMIT almost never sees them). If the area has almost nothing in the remaining classes
              (less than MIN_MASS), the variable is not used: otherwise the whole Earth would be "different"
              because of a sensor.
Module similarity = 1 − mean distance over the variables present on both sides. The cap keeps a variable that is
out of reach (390 K by day on the Moon) from crushing the whole module.
"""

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .. import db

CAP = 3.0
MIN_MASS = 0.25
PRESENT_SHARE = 0.002


@dataclass
class Variable:
    key: str
    label: str
    mode: str                         # abs, rank, deciles, hellinger
    table: str
    columns: list
    unit: str = ""
    compute: Optional[str] = None     # "difference": columns[0] − columns[1]
    classes: Optional[list] = None    # short class names (hellinger)
    raw_unit: str = ""                # rank: unit of the real value, shown next to the level (m, per 1,000 km²...)
    per_1000km2: bool = False         # rank: number of objects per cell, shown per 1,000 km² (H3 cells are smaller
                                      # on Mars and the Moon)


@dataclass
class EarthData:
    """Variables of a module for every Earth cell (aligned on Earth.cells)."""
    values: dict = field(default_factory=dict)        # key -> float32 (n,) or (n, k)
    scales: dict = field(default_factory=dict)        # key -> float
    reliability: Optional[np.ndarray] = None          # float32 (n,), NaN without data
    raw: dict = field(default_factory=dict)           # key -> raw values (before ranking), for the detail
    present: dict = field(default_factory=dict)       # key -> classes present somewhere on the Earth (hellinger)
    bounds: dict = field(default_factory=dict)        # key -> (2nd, 98th percentile) over the Earth, for display


class ModuleScore:
    key = ""
    name = ""
    folder = ""
    bodies = ("earth", "mars", "moon")
    variables: list = []
    reliability = ("", "fiabilite")    # (table, column) in the module's Parquet files
    suffixes: dict = {}                # table -> file suffix (topography: _b500)
    default_weight = 1.0

    def __init__(self):
        self._sorted = {}              # (body, key) -> sorted values of the body, for ranks

    # ------------------------------------------------------------------ files
    def path(self, table, body):
        return db.parquet_path(self.folder, table, body, self.suffixes.get(table, ""))

    def available(self, body) -> bool:
        return body in self.bodies and any(self.path(t, body).is_file() for t in self._tables())

    def _tables(self) -> dict:
        t = {}
        for v in self.variables:
            t.setdefault(v.table, set()).update(v.columns)
        t.setdefault(self.reliability[0], set()).add(self.reliability[1])
        return t

    def _read(self, body, cells=None) -> dict:
        """{table: {column: values aligned on the table's h3 column}}; missing tables are skipped."""
        out = {}
        for table, names in self._tables().items():
            f = self.path(table, body)
            if not f.is_file():
                continue
            present = set(db.columns(f))
            out[table] = db.read(f, sorted(n for n in names if n in present), cells)
        return out

    @staticmethod
    def _value(v: Variable, data: dict, n: int, pos) -> Optional[np.ndarray]:
        """Values of a variable over n rows; pos: position of each table row in the output."""
        t = data.get(v.table)
        if t is None:
            return None
        cols = []
        for c in v.columns:
            x = np.full(n, np.nan)
            if c in t:
                x[pos[v.table]] = t[c]
            cols.append(x)
        if all(np.isnan(c).all() for c in cols):
            return None
        if v.compute == "difference":
            return cols[0] - cols[1]
        return cols[0] if len(cols) == 1 else np.column_stack(cols)

    # ------------------------------------------------------------------ Earth (at startup)
    def load_earth(self, cells: np.ndarray, to_ints) -> Optional[EarthData]:
        data = self._read("earth")
        if not data:
            return None
        pos = {t: np.searchsorted(cells, to_ints(d["h3"])) for t, d in data.items()}
        n = len(cells)
        D = EarthData()
        presence = np.zeros(n, dtype=bool)
        for v in self.variables:
            x = self._value(v, data, n, pos)
            if x is None:
                continue
            ok = np.isfinite(x) if x.ndim == 1 else np.isfinite(x).any(axis=1)
            presence |= ok
            if v.mode == "rank":
                D.raw[v.key] = x.astype(np.float32)
                x = rank(x)
            D.values[v.key] = x.astype(np.float32)
            if v.mode in ("abs", "rank"):
                D.scales[v.key] = std_dev(x)
                D.bounds[v.key] = (0.0, 1.0) if v.mode == "rank" else quantiles(x, 0.02, 0.98)
            elif v.mode == "deciles":
                D.scales[v.key] = std_dev(x[:, x.shape[1] // 2])
                D.bounds[v.key] = (0.0, quantiles(x[:, -1], 0.0, 0.98)[1])
            elif v.mode == "hellinger":
                measured = np.isfinite(x).any(axis=1)
                D.present[v.key] = (np.nan_to_num(x[measured]) > 0.01).mean(axis=0) >= PRESENT_SHARE
        if not D.values:
            return None
        table_r, col_r = self.reliability
        r = np.full(n, np.nan)
        if table_r in data and col_r in data[table_r]:
            r[pos[table_r]] = data[table_r][col_r]
        D.reliability = np.where(presence, np.clip(np.nan_to_num(r, nan=1.0), 0, 1), np.nan).astype(np.float32)
        return D

    # ------------------------------------------------------------------ reference
    def reference(self, cells: list, weights: np.ndarray, body: str) -> Optional[dict]:
        """Mean of the area per variable, or None if the module has no data on the area."""
        if not self.available(body):
            return None
        data = self._read(body, cells)
        if not data:
            return None
        index = {c: i for i, c in enumerate(cells)}
        n = len(cells)
        pos = {t: np.array([index[c] for c in d["h3"]], dtype=np.int64) for t, d in data.items()}
        ref = {"variables": {}, "reliability": None, "raw": {}}
        for v in self.variables:
            x = self._value(v, data, n, pos)
            if x is None:
                continue
            if v.mode == "rank":
                ref["raw"][v.key] = weighted_mean(x, weights)       # real value, for display
                s = self._sorted_values(body, v)
                x = np.where(np.isfinite(x), np.searchsorted(s, x, side="left") / max(len(s) - 1, 1), np.nan)
            m = weighted_mean(x, weights)
            if (np.ndim(m) == 0 and math.isfinite(m)) or (np.ndim(m) == 1 and np.isfinite(m).any()):
                ref["variables"][v.key] = m
        if not ref["variables"]:
            return None
        table_r, col_r = self.reliability
        if table_r in data and col_r in data[table_r]:
            r = np.full(n, np.nan)
            r[pos[table_r]] = data[table_r][col_r]
            ref["reliability"] = weighted_mean(r, weights)
        return ref

    def _sorted_values(self, body, v: Variable) -> np.ndarray:
        k = (body, v.key)
        if k not in self._sorted:
            self._sorted[k] = db.sorted_values(self.path(v.table, body), v.columns[0])
        return self._sorted[k]

    # ------------------------------------------------------------------ score
    def distance(self, v: Variable, ref: dict, D: EarthData, rows=slice(None)):
        """(distance from 0 to 1, present on both sides) of variable v, or None if it cannot be compared."""
        if v.key not in ref["variables"] or v.key not in D.values:
            return None
        r, x = ref["variables"][v.key], D.values[v.key][rows]
        if v.mode == "hellinger":
            r = np.where(D.present[v.key], np.asarray(r, dtype=float), np.nan)
            if np.nansum(r) < MIN_MASS:
                return None
            return hellinger(x, r)
        if v.mode == "deciles":
            keep = np.isfinite(r)
            ok = np.isfinite(x[:, keep]).all(axis=1)
            e = np.abs(x[:, keep] - r[keep]).mean(axis=1) / D.scales[v.key]
            return np.minimum(np.nan_to_num(e), CAP) / CAP, ok
        ok = np.isfinite(x)
        return np.minimum(np.nan_to_num(np.abs(x - r) / D.scales[v.key]), CAP) / CAP, ok

    def score(self, ref: dict, D: EarthData) -> np.ndarray:
        n = len(D.reliability)
        total = np.zeros(n, dtype=np.float32)
        count = np.zeros(n, dtype=np.float32)
        for v in self.variables:
            e = self.distance(v, ref, D)
            if e is None:
                continue
            d, ok = e
            total += np.where(ok, d, 0).astype(np.float32)
            count += ok
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(count > 0, 1 - total / count, np.nan).astype(np.float32)

    def description(self) -> dict:
        return {"key": self.key, "name": self.name, "bodies": list(self.bodies), "default_weight": self.default_weight,
                "variables": [{"key": v.key, "label": v.label, "mode": v.mode, "unit": v.unit} for v in self.variables]}


# ---------------------------------------------------------------------- helpers
def rank(x: np.ndarray) -> np.ndarray:
    """Rank from 0 (lowest) to 1 (highest); ties get the lowest rank, as in the preprocessing modules."""
    r = np.full(x.shape, np.nan, dtype=np.float32)
    ok = np.isfinite(x)
    v = x[ok]
    if len(v) > 1:
        r[ok] = np.searchsorted(np.sort(v), v, side="left") / (len(v) - 1)
    return r


def quantiles(x: np.ndarray, a: float, b: float):
    v = x[np.isfinite(x)]
    return (float(np.quantile(v, a)), float(np.quantile(v, b))) if len(v) else (0.0, 1.0)


def std_dev(x: np.ndarray) -> float:
    v = x[np.isfinite(x)]
    s = float(np.std(v)) if len(v) > 1 else 0.0
    return s if s > 1e-9 else 1.0


def weighted_mean(x: np.ndarray, weights: np.ndarray):
    if x.ndim == 1:
        ok = np.isfinite(x)
        return float(np.sum(x[ok] * weights[ok]) / np.sum(weights[ok])) if ok.any() else math.nan
    return np.array([weighted_mean(x[:, j], weights) for j in range(x.shape[1])])


def hellinger(x: np.ndarray, r: np.ndarray):
    """Hellinger distance (0 to 1) over the classes measured by the reference, plus a "rest" class."""
    keep = np.isfinite(r)
    rr = np.clip(r[keep], 0, None)
    rr = np.append(rr, max(0.0, 1 - rr.sum()))
    xs = np.clip(x[:, keep], 0, None)
    ok = np.isfinite(xs).all(axis=1)
    xs = np.nan_to_num(xs)
    xs = np.column_stack([xs, np.clip(1 - xs.sum(axis=1), 0, None)])
    rr = rr / rr.sum() if rr.sum() > 0 else rr
    tot = xs.sum(axis=1, keepdims=True)
    xs = np.divide(xs, tot, out=np.zeros_like(xs), where=tot > 0)
    bc = np.sqrt(xs * rr).sum(axis=1)
    return np.sqrt(np.clip(1 - bc, 0, 1)).astype(np.float32), ok
