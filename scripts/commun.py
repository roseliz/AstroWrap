"""Common tools for modules (imported from modules_pretraitement/*/scripts)."""
from __future__ import annotations

from pathlib import Path


def reconstruire_duckdb(dossier: Path, corps: str) -> Path:
    """Recreates `<folder>/<body>.duckdb` from all body Parquet files in the directory
    (one table per file, with the same name).

    The DuckDB file is simply a copy of the Parquet files: it is completely rebuilt on every write. This
    avoids the "database file created with a newer version of DuckDB" error when the folder comes from
    another machine (Windows, Colab) whose DuckDB version is newer than the one in `.venv`."""
    import duckdb
    dossier = Path(dossier)
    base = dossier / f"{corps}.duckdb"
    for f in (base, base.with_name(base.name + ".wal")):
        try:
            f.unlink(missing_ok=True)
        except PermissionError:
            raise SystemExit(f"{f} est ouvert par un autre programme (notebook, DBeaver…) : le fermer et relancer")
    with duckdb.connect(str(base)) as con:
        for p in sorted(dossier.glob(f"*_{corps}_h3_*.parquet")):
            con.execute(f"CREATE TABLE {p.stem} AS SELECT * FROM read_parquet('{p.as_posix()}')")
    return base


def verifier_espace(dossier: Path, go_necessaires: float, quoi: str) -> None:
    """Arrête le module avant un gros téléchargement s'il n'y a pas la place sur le disque."""
    import shutil
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    libre = shutil.disk_usage(dossier).free / 1e9
    if libre < go_necessaires:
        raise SystemExit(
            f"Pas assez de place pour {quoi} : {libre:.1f} Go libres dans {dossier}, il en faut ~{go_necessaires:.0f}.\n"
            "  Voir ce qui prend la place : du -sh cache/* inputs/* ; df -h .\n"
            "  /tmp est souvent petit (et vidé au redémarrage) : mieux vaut cloner le dépôt dans le dossier personnel.")


def court(chemin, racine) -> str:
    """Chemin à afficher : relatif à la racine du dépôt, ou complet s'il est ailleurs (cache/ sur un SSD)."""
    try:
        return Path(chemin).relative_to(racine).as_posix()
    except ValueError:
        return str(chemin)
