"""Outils communs aux modules (importés depuis modules_pretraitement/*/scripts)."""
from __future__ import annotations

from pathlib import Path


def reconstruire_duckdb(dossier: Path, corps: str) -> Path:
    """Recrée <dossier>/<corps>.duckdb à partir de tous les Parquet du corps dans le dossier
    (une table par fichier, du même nom).

    Le fichier DuckDB n'est qu'une copie des Parquet : on le refait entièrement à chaque écriture. Cela
    évite l'erreur « database file created with a newer version of DuckDB » quand le dossier vient d'une
    autre machine (Windows, Colab) dont DuckDB est plus récent que celui de .venv."""
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
