"""Check that the machine can run the modules: Python, packages, credentials, inputs, disk.

    python scripts/verifier.py                      # all modules
    python scripts/verifier.py thermal_light_extrems

Exit code 1 if a mandatory item is missing.
"""

from __future__ import annotations

import importlib.util
import netrc
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
IMPORTS = {"pyhdf": "pyhdf", "netcdf4": "netCDF4"}   # nom pip -> nom à importer, quand ils diffèrent
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # console Windows (cp1252) : ✓ ✗
COULEURS = sys.stdout.isatty()
ok_global = True


def ligne(etat: str, quoi: str, detail: str = "") -> None:
    symbole = {"ok": ("✓", 32), "ko": ("✗", 31), "info": ("!", 33)}[etat]
    s = f"\033[{symbole[1]}m{symbole[0]}\033[0m" if COULEURS else symbole[0]
    print(f"  {s} {quoi}" + (f" — {detail}" if detail else ""))


def echec(quoi: str, detail: str) -> None:
    global ok_global
    ok_global = False
    ligne("ko", quoi, detail)


def paquets(fichier: Path) -> list[str]:
    noms = []
    for l in fichier.read_text(encoding="utf-8").splitlines():
        l = l.split("#")[0].strip()
        if l.startswith("-r "):
            noms += paquets((fichier.parent / l[3:].strip()).resolve())
        elif l:
            noms.append(re.split(r"[<>=!~\[ ;]", l)[0].lower())
    return noms


# Entrées à copier à la main (voir le README de chaque module) : nom, dossier, usage, description
MCD = ("MCD", "inputs/mcd", "Mars", "clim_01_me.nc … clim_12_me.nc de la Mars Climate Database (sur demande au LMD)")
MANUELLES = {
    "thermal_light_extrems": [MCD],
    "wind_erosion_atmosphere": [MCD, ("MGD3", "inputs/wind_erosion_atmosphere/mgd3", "les dunes de Mars",
                                      "dossier Shapefiles de la Mars Global Digital Dune Database (USGS)")],
    "volatiles_hydrology_ice": [MCD],
    "geology_mineralogy": [("GLiM", "inputs/geology_mineralogy/glim", "les roches de la Terre",
                            "dossier LiMW_GIS 2015.gdb"),
                           ("Carte géologique de la Lune", "inputs/geology_mineralogy/carte_lune", "les roches de la Lune",
                            "GeoUnits.shp (+ .dbf, .shx, .prj) de la Unified Geologic Map of the Moon")],
}


def entrees(module: str) -> list[dict]:
    return [{"nom": n, "dossier": RACINE / d, "usage": u, "description": t} for n, d, u, t in MANUELLES.get(module, [])]


def est_module(p: Path) -> bool:
    return p.is_dir() and (p / "scripts").is_dir() and (p / "requirements.txt").is_file()


def identifiant_earthdata() -> bool:
    if os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD"):
        return True
    env = RACINE / ".env"                                    # EARTHDATA_* ou USERNAME_EARTHACCESS / PASSWORD_EARTHACCESS
    if env.is_file():
        noms = {l.split("=", 1)[0].strip().removeprefix("export ").strip() for l in
                env.read_text(encoding="utf-8", errors="ignore").splitlines() if "=" in l and not l.lstrip().startswith("#")}
        if {"EARTHDATA_USERNAME", "EARTHDATA_PASSWORD"} <= noms or {"USERNAME_EARTHACCESS", "PASSWORD_EARTHACCESS"} <= noms:
            return True
    for nom in (".netrc", "_netrc"):
        try:
            if netrc.netrc(Path.home() / nom).authenticators("urs.earthdata.nasa.gov"):
                return True
        except (FileNotFoundError, netrc.NetrcParseError):
            pass
    return False


def main() -> int:
    modules = sys.argv[1:] or sorted(p.name for p in (RACINE / "modules_pretraitement").iterdir() if est_module(p))

    print("Système")
    v = sys.version_info
    if v >= (3, 9):
        ligne("ok", f"Python {v.major}.{v.minor}", sys.executable)
    else:
        echec(f"Python {v.major}.{v.minor}", "il faut 3.9 ou plus")
    if sys.prefix == sys.base_prefix:
        ligne("info", "environnement .venv non activé", "activez-le avant de lancer un module")
    # cache/ peut être un lien vers un autre disque (SSD) : c'est là que vont les téléchargements
    cache = RACINE / "cache"
    libre = shutil.disk_usage(cache if cache.exists() else RACINE).free / 1e9
    if libre >= 10:
        ligne("ok", f"{libre:.0f} Go libres sur le disque")
    else:
        echec(f"{libre:.0f} Go libres sur le disque", "prévoir au moins 10 Go")
    try:
        ram = int(re.search(r"MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text()).group(1)) / 1e6
        ligne("ok" if ram >= 8 else "info", f"{ram:.0f} Go de RAM", "" if ram >= 8 else "la Terre en demande ~8 : un corps à la fois")
    except (OSError, AttributeError):
        pass

    print("Paquets Python")
    exigences = [RACINE / "modules_pretraitement" / m / "requirements.txt" for m in modules]
    noms = sorted({n for f in exigences if f.is_file() for n in paquets(f)})
    manquants = [n for n in noms if importlib.util.find_spec(IMPORTS.get(n, n.replace("-", "_"))) is None]
    if manquants:
        echec(", ".join(manquants), "absents : pip install -r modules_pretraitement/<module>/requirements.txt")
    else:
        ligne("ok", f"{len(noms)} paquets des modules installés")

    print("Accès")
    # Earthdata est obligatoire pour les modules qui utilisent earthaccess (pas la topographie) ; facultatif quand
    # la ligne earthaccess de leur requirements.txt dit « optionnel »
    def usage_earthdata(m: str) -> str | None:
        f = RACINE / "modules_pretraitement" / m / "requirements.txt"
        lignes = [l for l in f.read_text(encoding="utf-8", errors="ignore").splitlines()
                  if l.strip().startswith("earthaccess")] if f.is_file() else []
        return None if not lignes else "facultatif" if all("optionnel" in l for l in lignes) else "obligatoire"
    besoin = [m for m in modules if usage_earthdata(m) == "obligatoire"]
    facultatif = [m for m in modules if usage_earthdata(m) == "facultatif"]
    if identifiant_earthdata():
        ligne("ok", "NASA Earthdata", "~/.netrc ou EARTHDATA_USERNAME")
    elif besoin:
        echec("NASA Earthdata", f"nécessaire pour {', '.join(besoin)} : EARTHDATA_USERNAME et EARTHDATA_PASSWORD dans .env, ou urs.earthdata.nasa.gov dans ~/.netrc")
    elif facultatif:
        ligne("info", "NASA Earthdata non configuré", f"facultatif pour {', '.join(facultatif)} (RGI 7.0 ; sinon Natural Earth seul)")
    else:
        ligne("info", "NASA Earthdata non configuré", "inutile pour " + ", ".join(modules))
    if shutil.which("gh") is None:
        ligne("info", "GitHub CLI absent", "nécessaire seulement pour scripts/releases.py")
    elif subprocess.run(["gh", "auth", "status"], capture_output=True).returncode:
        ligne("info", "GitHub CLI non connecté", "gh auth login, pour scripts/releases.py")
    else:
        ligne("ok", "GitHub CLI connecté")

    for m in modules:
        print(f"Module {m}")
        if not est_module(RACINE / "modules_pretraitement" / m):
            echec(m, "module inconnu (pas de scripts/ ni de requirements.txt)")
            continue
        liste = entrees(m)
        if not liste:
            ligne("ok", "aucune entrée à copier")
        for e in liste:
            n = sum(1 for f in e["dossier"].rglob("*") if f.is_file()) if e["dossier"].is_dir() else 0
            if n:
                ligne("ok", f"{e['nom']} : {n} fichiers", e["dossier"].relative_to(RACINE).as_posix())
            else:
                ligne("info", f"{e['nom']} absent, nécessaire pour {e['usage']}",
                      f"copier dans {e['dossier'].relative_to(RACINE).as_posix()}/ : {e['description']}")

    print()
    print("Prêt." if ok_global else "Il manque des éléments obligatoires (✗ ci-dessus).")
    return 0 if ok_global else 1


if __name__ == "__main__":
    sys.exit(main())
