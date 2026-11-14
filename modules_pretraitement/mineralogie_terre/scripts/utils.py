"""Shared helpers: repository paths, NASA Earthdata login, DuckDB with the h3 extension, DuckDB export."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]                 # repository root
MODULE = "mineralogie_terre"
CACHE_DIR = ROOT / "cache" / MODULE
CATALOG_DIR = CACHE_DIR / "catalogue"
CALIBRATION_DIR = CACHE_DIR / "calibration"
OUTPUT_DIR = ROOT / "pretreatment_data" / MODULE


def load_dotenv_credentials() -> None:
    """Read ROOT/.env (KEY=value lines) into EARTHDATA_USERNAME / EARTHDATA_PASSWORD, printing nothing.
    Variables already set in the environment take priority."""
    f = ROOT / ".env"
    if not f.is_file():
        return
    values = {}
    for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip().removeprefix("export ").strip()] = value.strip().strip("\"'")
    for target, names in (("EARTHDATA_USERNAME", ("EARTHDATA_USERNAME", "USERNAME_EARTHACCESS")),
                          ("EARTHDATA_PASSWORD", ("EARTHDATA_PASSWORD", "PASSWORD_EARTHACCESS"))):
        for name in names:
            if values.get(name) and target not in os.environ:
                os.environ[target] = values[name]


def earthdata_login():
    """Log in to NASA Earthdata with EARTHDATA_USERNAME / EARTHDATA_PASSWORD (environment or .env)."""
    import earthaccess
    if not (os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD")):
        load_dotenv_credentials()
    if not earthaccess.login(strategy="environment").authenticated:
        sys.exit("NASA Earthdata login failed: set EARTHDATA_USERNAME and EARTHDATA_PASSWORD (environment or .env)")
    return earthaccess


def duckdb_h3(con=None):
    """DuckDB connection with the community h3 extension loaded (installed on first use)."""
    import duckdb
    c = con or duckdb.connect()
    try:
        c.execute("LOAD h3")
    except duckdb.Error:
        c.execute("INSTALL h3 FROM community; LOAD h3")
    return c


def short_path(path: Path, root: Path = ROOT) -> str:
    """Return `path` relative to `root` when possible, for shorter log messages."""
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(path)


def rebuild_duckdb(folder: Path, body: str) -> Path:
    """Rebuild `{body}.duckdb` from scratch, with one table per `*_{body}_*.parquet` file in `folder`."""
    import duckdb

    folder = Path(folder)
    database = folder / f"{body}.duckdb"
    temporary = database.with_name(database.name + ".tmp")
    temporary.unlink(missing_ok=True)
    with duckdb.connect(str(temporary)) as con:
        for parquet in sorted(folder.glob(f"*_{body}_*.parquet")):
            table = parquet.stem.replace('"', "")
            source = str(parquet.resolve()).replace("'", "''")
            con.execute(f"CREATE TABLE \"{table}\" AS SELECT * FROM read_parquet('{source}')")
    # Replace the old database only once the new one is complete
    try:
        temporary.replace(database)
    except PermissionError:
        sys.exit(f"{database} is open in another program (notebook, DBeaver...): close it and run again.")
    return database
