"""Lance le prétraitement thermique (Lune, Terre, Mars) avec python, sans Jupyter.

    ./pipeline run thermal_light_extrems                          # les trois corps
    ./pipeline run thermal_light_extrems --corps moon mars
    ./pipeline run thermal_light_extrems --corps earth --zone -115 31 -109 37

Le code vit dans notebooks/pretraitement_thermique_3_corps.ipynb : ce fichier en exécute
les cellules dans l'ordre et remplace les paramètres par les options ci-dessous. Une seule
version du code à maintenir, que l'on passe par Jupyter ou par python.
Les résultats vont dans pretreatment_data/thermal_light_extrems/ à la racine du dépôt.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

NOTEBOOK = Path(__file__).resolve().parents[1] / "notebooks" / "pretraitement_thermique_3_corps.ipynb"
TOUS_LES_CORPS = ("moon", "earth", "mars")


def options() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--corps", nargs="+", choices=TOUS_LES_CORPS, default=list(TOUS_LES_CORPS),
                   help="corps à traiter (défaut : les trois)")
    p.add_argument("--annee", type=int, help="année des données Terre (défaut du notebook : 2023)")
    p.add_argument("--zone", type=float, nargs=4, metavar=("OUEST", "SUD", "EST", "NORD"),
                   help="limiter la Terre à une boîte lat/lon (calcul plus court, même téléchargement)")
    p.add_argument("--resolution", type=int, help="résolution H3 (défaut du notebook : 5)")
    p.add_argument("--mcd", type=Path, help="dossier clim_aveEUV de la Mars Climate Database "
                                            "(défaut : inputs/mcd à la racine du dépôt)")
    return p.parse_args()


def afficher(objet) -> None:
    """Remplace display() de Jupyter : les tableaux de contrôle s'impriment en entier."""
    try:
        import pandas as pd
        if isinstance(objet, pd.DataFrame):
            with pd.option_context("display.max_rows", 200, "display.max_columns", None, "display.width", 250):
                print(objet)
            return
    except ImportError:
        pass
    print(objet)


def remplacer(source: str, nom: str, valeur) -> tuple[str, bool]:
    """Remplace la ligne « NOM = ... » du notebook par « NOM = valeur »."""
    motif = re.compile(rf"^{nom}\s*=.*$", re.M)
    if not motif.search(source):
        return source, False
    return motif.sub(lambda _: f"{nom} = {valeur!r}", source, count=1), True


def main() -> int:
    args = options()
    parametres = {"FAIRE": {c: c in args.corps for c in TOUS_LES_CORPS}}
    if args.annee is not None:
        parametres["ANNEE_TERRE"] = args.annee
    if args.zone is not None:
        parametres["ZONE_TERRE"] = tuple(args.zone)
    if args.resolution is not None:
        parametres["RESOLUTION"] = args.resolution
    if args.mcd is not None:
        parametres["DOSSIER_MCD"] = str(args.mcd.expanduser().resolve())

    os.chdir(NOTEBOOK.parent)   # le notebook retrouve la racine du dépôt depuis son dossier

    cellules = [c for c in json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"] if c["cell_type"] == "code"]
    cellules = [("".join(c["source"]) if isinstance(c["source"], list) else c["source"]) for c in cellules]

    restants = dict(parametres)
    for i, s in enumerate(cellules):
        for nom in list(restants):
            s, fait = remplacer(s, nom, restants[nom])
            if fait:
                del restants[nom]
        cellules[i] = s
    if restants:
        sys.exit(f"Paramètres introuvables dans le notebook : {', '.join(restants)}")

    print("Paramètres :", ", ".join(f"{k}={v!r}" for k, v in parametres.items()), flush=True)
    espace = {"__name__": "__main__", "display": afficher}
    debut = time.time()
    for i, source in enumerate(cellules, 1):
        t = time.time()
        print(f"\n===== cellule {i}/{len(cellules)}", flush=True)
        exec(compile(source, f"{NOTEBOOK.name}, cellule {i}", "exec"), espace)
        print(f"----- cellule {i} : {time.time() - t:.0f} s", flush=True)
    print(f"\nTerminé en {(time.time() - debut) / 60:.1f} min.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
