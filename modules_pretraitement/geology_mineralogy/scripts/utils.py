"""Small helpers shared by the preprocessing script: disk checks, path display, DuckDB export."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def short_path(path: Path, root: Path) -> str:
    """Return `path` relative to `root` when possible, for shorter log messages."""
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(path)


def check_free_space(folder: Path, needed_gb: float, purpose: str) -> None:
    """Exit with a clear message if the disk holding `folder` has less than `needed_gb` GB free."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    free_gb = shutil.disk_usage(folder).free / 1e9
    if free_gb < needed_gb:
        sys.exit(f"Not enough disk space in {folder}: {free_gb:.1f} GB free, about {needed_gb:g} GB "
                 f"needed for {purpose}.")


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
