"""Read-only DuckDB connection over the Parquet files of pretreatment_data/.

The server queries the Parquet files (read_parquet), not the .duckdb files: a .duckdb written by DuckDB 2.0 does
not open with DuckDB 1.x ("version 999" error), whereas Parquet files can be read by every version.
One connection for the server, one cursor per query.
"""

import threading
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa

from ..core import config

_connection = None
_lock = threading.Lock()


def connection():
    global _connection
    with _lock:
        if _connection is None:
            settings = {"memory_limit": config.DUCKDB_MEMORY, "threads": config.DUCKDB_THREADS}
            if config.DUCKDB_TEMP:
                settings["temp_directory"] = config.DUCKDB_TEMP
            _connection = duckdb.connect(":memory:", config=settings)
        return _connection


def cursor():
    return connection().cursor()


def parquet_path(folder: str, table: str, body: str, suffix: str = "") -> Path:
    return config.DATA_DIR / folder / f"{table}_{body}_h3_{config.RESOLUTION}{suffix}.parquet"


def columns(f: Path) -> list:
    return [r[0] for r in cursor().execute("SELECT name FROM parquet_schema(?)", [str(f)]).fetchall()]


def read(f: Path, names: list, cells=None) -> dict:
    """Columns `names` (+ h3) of the Parquet file, as numpy arrays; only the given cells if `cells` is set."""
    cur = cursor()
    cols = ", ".join(f'"{c}"' for c in ["h3"] + list(names))
    if cells is None:
        r = cur.execute(f"SELECT {cols} FROM read_parquet(?)", [str(f)])
    else:
        cur.register("requested_cells", pa.table({"h3": pa.array(list(cells), type=pa.string())}))
        r = cur.execute(f"SELECT {cols} FROM read_parquet(?) WHERE h3 IN (SELECT h3 FROM requested_cells)", [str(f)])
    d = r.fetchnumpy()
    out = {"h3": np.asarray(d["h3"], dtype=object)}
    for c in names:
        v = d[c]
        out[c] = np.asarray(v.filled(np.nan) if hasattr(v, "filled") else v, dtype=np.float64)
    return out


def sorted_values(f: Path, name: str) -> np.ndarray:
    """Every value of a column, sorted (used to rank a value within its body)."""
    d = cursor().execute(f'SELECT CAST("{name}" AS DOUBLE) AS v FROM read_parquet(?) '
                         f'WHERE "{name}" IS NOT NULL AND isfinite(CAST("{name}" AS DOUBLE)) ORDER BY 1',
                         [str(f)]).fetchnumpy()
    return np.asarray(d["v"], dtype=np.float32)
