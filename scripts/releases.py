"""Sharing module results via the repository's GitHub releases.

    python scripts/releases.py publier   thermal_light_extrems --note "Earth 2023, Moon, Mars"
    python scripts/releases.py recuperer thermal_light_extrems [--tag <release>]
    python scripts/releases.py liste     [thermal_light_extrems]

One release per execution, "<module>-YYYY-MM-DD-HHMM", containing the zip of `pretreatment_data/<module>/`.
Uses GitHub CLI (`gh`), authenticated via `gh auth login`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
LIMITE = 2 * 1024**3   # taille maximale d'un fichier attaché à une release GitHub


def gh(*args: str, capturer: bool = True) -> str:
    if shutil.which("gh") is None:
        sys.exit("GitHub CLI (gh) introuvable : installez-le (https://cli.github.com) puis gh auth login")
    r = subprocess.run(["gh", *args], cwd=RACINE, capture_output=capturer, text=True)
    if r.returncode:
        sys.exit((r.stderr or "").strip() or f"échec : gh {' '.join(args)}")
    return r.stdout if capturer else ""


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=RACINE, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "?"


def sha256(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def verifier_module(module: str) -> None:
    if not (RACINE / "modules_pretraitement" / module).is_dir():
        connus = sorted(p.name for p in (RACINE / "modules_pretraitement").iterdir() if p.is_dir())
        sys.exit(f"Module inconnu : {module}. Modules : {', '.join(connus)}")


def releases() -> list[dict]:
    return json.loads(gh("release", "list", "--limit", "200", "--json", "tagName,createdAt"))


def publier(module: str, note: str) -> None:
    verifier_module(module)
    dossier = RACINE / "pretreatment_data" / module
    fichiers = sorted(f for f in dossier.rglob("*") if f.is_file() and f.name != "README.md") if dossier.is_dir() else []
    if not fichiers:
        sys.exit(f"Aucun résultat dans {dossier} : lancez d'abord le module (voir modules_pretraitement/{module}/README.md)")
    date = dt.datetime.now().strftime("%Y-%m-%d-%H%M")
    tag = f"{module}-{date}"
    commit = git("rev-parse", "--short", "HEAD")
    if git("status", "--porcelain", "modules_pretraitement"):
        commit += " (avec des modifications non commitées dans modules_pretraitement/)"
    lignes = [note, ""] if note else []
    lignes += [f"Résultats du module `{module}`, produits sur `{platform.node()}` avec le commit {commit}.", "",
               "| Fichier | Taille | SHA-256 |", "|---|---:|---|"]
    for f in fichiers:
        lignes.append(f"| `{f.relative_to(dossier).as_posix()}` | {f.stat().st_size / 1e6:.1f} Mo | `{sha256(f)[:16]}` |")
    lignes += ["", f"Récupérer : `python scripts/releases.py recuperer {module} --tag {tag}`"]
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(shutil.make_archive(str(Path(tmp) / module), "zip", root_dir=dossier.parent, base_dir=module))
        print(f"Archive {archive.name} : {archive.stat().st_size / 1e6:.0f} Mo, {len(fichiers)} fichiers")
        if archive.stat().st_size > LIMITE:
            sys.exit("Archive de plus de 2 Go (limite GitHub) : publiez un corps à la fois.")
        notes = Path(tmp) / "notes.md"
        notes.write_text("\n".join(lignes), encoding="utf-8")
        gh("release", "create", tag, str(archive), "--title", f"{module} — {date}", "--notes-file", str(notes), capturer=False)
    print(f"Release publiée : {tag}")


def recuperer(module: str, tag: str | None) -> None:
    verifier_module(module)
    if not tag:
        du_module = [r for r in releases() if r["tagName"].startswith(module + "-")]
        if not du_module:
            sys.exit(f"Aucune release de résultats pour {module}.")
        tag = max(du_module, key=lambda r: r["createdAt"])["tagName"]
    destination = RACINE / "pretreatment_data"
    with tempfile.TemporaryDirectory() as tmp:
        print(f"Téléchargement de {tag}...")
        gh("release", "download", tag, "--pattern", "*.zip", "--dir", tmp)
        for archive in Path(tmp).glob("*.zip"):
            with zipfile.ZipFile(archive) as z:
                if any(Path(n).is_absolute() or ".." in Path(n).parts for n in z.namelist()):
                    sys.exit(f"Archive refusée (chemin suspect) : {archive.name}")
                z.extractall(destination)
    for f in sorted((destination / module).rglob("*")):
        if f.is_file() and f.name != "README.md":
            print(f"  {f.relative_to(RACINE).as_posix():60s} {f.stat().st_size / 1e6:8.1f} Mo")


def liste(module: str | None) -> None:
    for r in sorted(releases(), key=lambda r: r["createdAt"], reverse=True):
        if module is None or r["tagName"].startswith(module + "-"):
            print(f"{r['createdAt'][:16].replace('T', ' ')}  {r['tagName']}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="action", required=True)
    a = s.add_parser("publier"); a.add_argument("module"); a.add_argument("--note", default="")
    a = s.add_parser("recuperer"); a.add_argument("module"); a.add_argument("--tag")
    a = s.add_parser("liste"); a.add_argument("module", nargs="?")
    args = p.parse_args()
    if args.action == "publier":
        publier(args.module, args.note)
    elif args.action == "recuperer":
        recuperer(args.module, args.tag)
    else:
        liste(args.module)
    return 0


if __name__ == "__main__":
    sys.exit(main())
