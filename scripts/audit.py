"""Audit module results: missing, impossible or suspicious data, benchmark sites.

    ./pipeline audit thermal_light_extrems              # report in logs/audit_<module>.html
    python scripts/audit.py <module> [--dossier D] [--sans-cartes]

Reads all pretreatment_data/<module>/*_{earth,mars,moon}_h3_<res>[_suffixe].parquet files and performs,
for each table and each body:

  1. structure     duplicate cells, invalid H3 IDs, expected cell count,
                   same columns across all three bodies
  2. missing       share of NaNs per column, and per 10° latitude band (an empty band in the middle
                   of full bands indicates a read gap)
  3. bounds        shares between 0 and 1, compositions summing to 1, and the physical bounds from file
                   modules_pretraitement/<module>/audit.csv
  4. suspicious    constant column, abnormally frequent repeated value, two identical columns,
                   very few distinct values (copied coarse grid)
  5. benchmarks    value (or within-body rank) of known sites, compared to the expected
                   range from literature (audit.csv, with the source of each range)

Levels: ERROR (impossible or false data), WARNING (needs explanation), INFO.
The HTML report also contains a map per column and per body.
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import re
import sys
from pathlib import Path

import h3
import numpy as np
import pandas as pd

RACINE = Path(__file__).resolve().parents[1]
NOMS = {"earth": "Terre", "mars": "Mars", "moon": "Lune"}
MOTIF = re.compile(r"^(?P<table>.+)_(?P<corps>earth|mars|moon)_h3_(?P<res>\d+)(?P<suffixe>_\w+)?$")
CLES = {"body", "resolution", "h3"}
# Colonnes de comptage ou de qualité : pas de contrôle « suspect » (elles sont souvent constantes par construction)
COMPTES = re.compile(r"^(n_.*|.*pixel_count|n_pixels|coverage|reliability|couverture.*|fiabilite|.*resolution.*|base.*_m)$")
FRACTION = re.compile(r"^(part_|comp_|litho_)|(_fraction|^coverage|^reliability|^couverture|^fiabilite|^taux_)")


class Constats:
    def __init__(self):
        self.lignes: list[dict] = []

    def ajouter(self, niveau, table, corps, colonne, message):
        self.lignes.append({"niveau": niveau, "table": table, "corps": corps, "colonne": colonne or "", "constat": message})


def lire_regles(module: str) -> pd.DataFrame:
    f = RACINE / "modules_pretraitement" / module / "audit.csv"
    if not f.is_file():
        return pd.DataFrame(columns=["type", "table", "colonne", "corps", "site", "lat", "lon", "mesure", "min", "max", "source"])
    return pd.read_csv(f, comment="#", skipinitialspace=True, dtype={"site": str, "source": str}).fillna({"site": "", "source": ""})


def latitudes(cellules: np.ndarray) -> np.ndarray:
    return np.array([h3.cell_to_latlng(c) for c in cellules])


def carte_png(lat, lon, v, titre) -> str | None:
    """Carte cylindrique : moyenne des cellules par case de 0,5°, cases vides en gris."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    ok = np.isfinite(v)
    i = np.clip(((90 - lat) * 2).astype(int), 0, 359)
    j = np.clip(((lon + 180) * 2).astype(int), 0, 719)
    som = np.zeros((360, 720)); nb = np.zeros((360, 720)); vu = np.zeros((360, 720), bool)
    np.add.at(som, (i[ok], j[ok]), v[ok]); np.add.at(nb, (i[ok], j[ok]), 1); vu[i, j] = True
    img = np.where(nb > 0, som / np.maximum(nb, 1), np.nan)
    fig, ax = plt.subplots(figsize=(5.2, 2.9), dpi=90)
    ax.imshow(np.where(vu, np.nan, 0), extent=(-180, 180, -90, 90), cmap="Greys", vmin=-1, vmax=1)
    if ok.any():
        bas, haut = np.nanpercentile(v[ok], [1, 99])
        im = ax.imshow(img, extent=(-180, 180, -90, 90), cmap="viridis", vmin=bas, vmax=haut if haut > bas else bas + 1e-9)
        fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
    ax.set_title(titre, fontsize=8); ax.tick_params(labelsize=6)
    ax.set_facecolor("#ddd")
    buf = io.BytesIO(); fig.tight_layout(); fig.savefig(buf, format="png"); plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def auditer_table(nom, corps, res, t: pd.DataFrame, regles: pd.DataFrame, c: Constats, cartes: dict | None):
    n = len(t)
    # --- 1. structure
    if "h3" not in t:
        c.ajouter("ERREUR", nom, corps, "h3", "pas de colonne h3"); return
    d = int(t["h3"].duplicated().sum())
    if d:
        c.ajouter("ERREUR", nom, corps, "h3", f"{d:,} cellules en double")
    echantillon = t["h3"].sample(min(n, 20000), random_state=0) if n else t["h3"]
    invalides = sum(not h3.is_valid_cell(x) or h3.get_resolution(x) != res for x in echantillon)
    if invalides:
        c.ajouter("ERREUR", nom, corps, "h3", f"{invalides} identifiants invalides ou de mauvaise résolution sur {len(echantillon)} lus")
    attendu = h3.get_num_cells(res)
    if corps in ("mars", "moon") and n != attendu:
        c.ajouter("ATTENTION", nom, corps, "h3", f"{n:,} cellules au lieu de {attendu:,} (toute la surface)")
    if "body" in t and (t["body"] != corps).any():
        c.ajouter("ERREUR", nom, corps, "body", "la colonne body ne correspond pas au fichier")

    num = [k for k in t.columns if k not in CLES and pd.api.types.is_numeric_dtype(t[k])]
    ll = latitudes(t["h3"].to_numpy())
    lat, lon = ll[:, 0], ll[:, 1]
    bandes = np.clip(((lat + 90) // 10).astype(int), 0, 17)
    stats, vides, constantes, grossieres, trous_zone = [], [], [], [], {}
    for k in num:
        v = t[k].to_numpy(dtype=float)
        ok = np.isfinite(v)
        nan = 1 - ok.mean() if n else 0
        vals = v[ok]
        nu = int(pd.Series(vals).nunique()) if ok.any() else 0
        st = {"colonne": k, "nan_%": round(100 * nan, 1), "uniques": nu}
        if ok.any():
            q = np.percentile(vals, [0, 1, 50, 99, 100])
            st.update({"min": q[0], "p1": q[1], "p50": q[2], "p99": q[3], "max": q[4]})
        stats.append(st)
        # --- 2. manquants
        if nan == 1:
            vides.append(k)
            continue
        if nan > 0:
            # trou localisé : cases de 10° × 20° vides alors que le reste de leur bande de latitude est plein
            cases = pd.DataFrame({"b": bandes, "l": np.clip(((lon + 180) // 20).astype(int), 0, 17), "vide": ~ok})
            g = cases.groupby(["b", "l"])["vide"]
            part = g.mean().where(g.size() >= 50).unstack()          # cases d'au moins 50 cellules (pas les îles)
            for bb, ligne in part.iterrows():
                ligne = ligne.dropna()
                trous_l = [int(l) for l, x in ligne.items() if x > 0.5]
                if trous_l and len(trous_l) < len(ligne) and ligne.drop(trous_l).median() < 0.05:
                    plages, debut = [], trous_l[0]
                    for x, y in zip(trous_l, trous_l[1:] + [None]):
                        if y != x + 1:
                            plages.append(f"{debut * 20 - 180}° à {x * 20 - 160}°"); debut = y
                    nb_vides = int(cases[(cases.b == bb) & cases.l.isin(trous_l)]["vide"].sum())
                    cle = (f"latitudes {bb * 10 - 90}° à {bb * 10 - 80}°, longitudes {', '.join(plages)} "
                           f"({nb_vides:,} cellules)")
                    trous_zone.setdefault(cle, {"cols": [], "b": bb, "l": trous_l})["cols"].append(k)
            par_bande = pd.Series(~ok).groupby(bandes).mean()
            pleines = par_bande[par_bande < 0.05]
            trous = [b for b, x in par_bande.items() if x > 0.95 and (b - 1 in pleines.index and b + 1 in pleines.index)]
            if trous:
                c.ajouter("ERREUR", nom, corps, k, "bande(s) de latitude vides entre des bandes pleines : "
                          + ", ".join(f"{b * 10 - 90}° à {b * 10 - 80}°" for b in trous))
            if nan > 0.02:
                zones_vides = ", ".join(f"{b * 10 - 90}°…{b * 10 - 80}° : {x:.0%}" for b, x in par_bande.items() if x > 0.5)
                c.ajouter("INFO", nom, corps, k, f"{nan:.1%} de cellules vides" + (f" (surtout {zones_vides})" if zones_vides else ""))
        # --- 3. bornes génériques
        if FRACTION.search(k) and ((vals < -1e-6) | (vals > 1 + 1e-6)).any():
            m = int(((vals < -1e-6) | (vals > 1 + 1e-6)).sum())
            c.ajouter("ERREUR", nom, corps, k, f"{m:,} valeurs hors de [0, 1] (min {vals.min():.3g}, max {vals.max():.3g})")
        # --- 4. suspects (pas sur les colonnes de comptage)
        if COMPTES.match(k):
            pass
        elif nu == 1:
            constantes.append(f"{k} = {vals[0]:.4g}")
        elif nu > 1:
            vc = pd.Series(vals).value_counts(normalize=True)
            top, part = vc.index[0], vc.iloc[0]
            if part > 0.3 and top not in (0.0, 1.0):
                c.ajouter("ATTENTION", nom, corps, k, f"{part:.0%} des cellules valent exactement {top:.4g} "
                          f"(de {vals.min():.4g} à {vals.max():.4g}) : la colonne distingue peu les cellules")
            elif np.nanstd(vals) < 1e-3 * max(abs(np.nanmean(vals)), 1e-9):
                c.ajouter("ATTENTION", nom, corps, k, f"quasi constante : {vals.min():.4g} à {vals.max():.4g}")
            if nu <= 5000 and ok.sum() > 100 * nu:
                grossieres.append(f"{k} ({nu:,})")
        if cartes is not None:
            png = carte_png(lat, lon, v, f"{NOMS[corps]} · {k}")
            if png:
                cartes.setdefault((nom, k), {})[corps] = png
    # trous connus (audit.csv, type trou : un point dans la zone vide et l'explication)
    connus = regles[(regles["type"] == "trou") & regles["table"].isin([nom, "*"]) & regles["corps"].isin([corps, "*"])]
    for message, z in trous_zone.items():
        explication = None
        for _, g in connus.iterrows():
            if (int((float(g["lat"]) + 90) // 10) == z["b"] and int((float(g["lon"]) + 180) // 20) in z["l"]
                    and any(re.fullmatch(g["colonne"], k) for k in z["cols"])):
                explication = f"{g['site']} ({g['source']})"
        if explication:
            c.ajouter("INFO", nom, corps, ", ".join(z["cols"]), f"zone vide connue : {message} — {explication}")
        else:
            c.ajouter("ERREUR", nom, corps, ", ".join(z["cols"]), f"zone vide au milieu de données : {message} ; fichier incomplet ?")
    if vides:
        c.ajouter("ATTENTION", nom, corps, ", ".join(vides), "entièrement vide(s)")
    if constantes:
        c.ajouter("ATTENTION", nom, corps, ", ".join(constantes), "constante(s) sur toutes les cellules : n'apportent rien à la comparaison")
    if grossieres:
        c.ajouter("INFO", nom, corps, ", ".join(grossieres), f"peu de valeurs différentes pour {n:,} cellules : "
                  "la grille de la source est plus grossière que les cellules (valeur recopiée)")
    # deux colonnes identiques (hors colonnes constantes et de comptage)
    utiles = [k for k in num if not COMPTES.match(k) and t[k].nunique() > 1]
    for i, a in enumerate(utiles):
        for b in utiles[i + 1:]:
            if np.array_equal(t[a].to_numpy(float), t[b].to_numpy(float), equal_nan=True):
                c.ajouter("ATTENTION", nom, corps, f"{a} = {b}", "colonnes identiques : l'une des deux est redondante")
    # compositions : somme à 1
    for prefixe in ("comp_", "litho_"):
        cols = [k for k in num if k.startswith(prefixe)]
        if len(cols) > 1:
            s = t[cols].sum(axis=1, min_count=1)
            pos = s[s > 0]
            hors = int(((pos - 1).abs() > 0.02).sum())
            if hors:
                c.ajouter("ERREUR", nom, corps, prefixe + "*", f"{hors:,} cellules dont la somme n'est pas 1 (ex. {pos[(pos - 1).abs() > 0.02].iloc[0]:.3f})")

    # --- 3 bis. bornes physiques et 5. témoins (audit.csv)
    r = regles[(regles["table"].isin([nom, "*"])) & (regles["corps"].isin([corps, "*"]))]
    for _, g in r[r["type"] == "borne"].iterrows():
        for k in [x for x in num if re.fullmatch(g["colonne"], x)]:
            v = t[k].to_numpy(float); ok = np.isfinite(v)
            hors = ok & ((v < g["min"]) | (v > g["max"]))
            if hors.any():
                ex = np.flatnonzero(hors)[:3]
                lieux = "; ".join(f"{v[e]:.4g} à ({lat[e]:.1f}, {lon[e]:.1f})" for e in ex)
                c.ajouter("ERREUR", nom, corps, k, f"{int(hors.sum()):,} cellules hors de [{g['min']:g}, {g['max']:g}] "
                          f"({g['source']}) — ex. {lieux}")
    index = pd.Index(t["h3"])
    temoins = []
    for _, g in r[r["type"] == "temoin"].iterrows():
        if g["colonne"] not in t:
            continue
        cel = h3.latlng_to_cell(float(g["lat"]), float(g["lon"]), res)
        j = index.get_indexer([cel])[0]
        v = float(t[g["colonne"]].iloc[j]) if j >= 0 else np.nan
        if g["mesure"] == "rang":
            col = t[g["colonne"]].astype(float)
            mesure = float((col < v).sum() + 0.5 * (col == v).sum()) / col.notna().sum() if np.isfinite(v) else np.nan
        else:
            mesure = v
        ok = np.isfinite(mesure) and g["min"] <= mesure <= g["max"]
        temoins.append({"site": g["site"], "colonne": g["colonne"], "mesure": g["mesure"],
                        "obtenu": mesure, "attendu": f"{g['min']:g} à {g['max']:g}", "verdict": "OK" if ok else "ÉCHEC",
                        "source": g["source"]})
        if not ok:
            c.ajouter("ERREUR" if np.isfinite(mesure) else "ATTENTION", nom, corps, g["colonne"],
                      f"témoin {g['site']} : {g['mesure']} = {mesure:.4g}, attendu {g['min']:g} à {g['max']:g} ({g['source']})")
    return pd.DataFrame(stats), pd.DataFrame(temoins)


def rapport_html(module, constats: pd.DataFrame, tableaux, cartes, sortie: Path):
    couleur = {"ERREUR": "#c0392b", "ATTENTION": "#d68910", "INFO": "#5d6d7e"}
    h = [f"<!doctype html><meta charset='utf-8'><title>Audit {module}</title>",
         "<style>body{font:14px system-ui,sans-serif;margin:24px;max-width:1500px;background:#fff;color:#222}"
         "table{border-collapse:collapse;margin:8px 0}td,th{border:1px solid #ddd;padding:3px 7px;font-size:12px;text-align:right}"
         "td:first-child,th:first-child{text-align:left}h2{margin-top:32px}.c{display:flex;flex-wrap:wrap;gap:6px}"
         "img{border:1px solid #eee}</style>",
         f"<h1>Audit de {html.escape(module)}</h1>"]
    resume = constats.groupby("niveau").size().reindex(["ERREUR", "ATTENTION", "INFO"]).fillna(0).astype(int) if len(constats) else {}
    h.append("<p>" + " · ".join(f"<b style='color:{couleur[k]}'>{v} {k.lower()}(s)</b>" for k, v in dict(resume).items()) + "</p>")
    h.append("<h2>Constats</h2><table><tr><th>niveau</th><th>table</th><th>corps</th><th>colonne</th><th style='text-align:left'>constat</th></tr>")
    ordre = {"ERREUR": 0, "ATTENTION": 1, "INFO": 2}
    for _, r in constats.sort_values("niveau", key=lambda s: s.map(ordre)).iterrows():
        h.append(f"<tr><td style='color:{couleur[r.niveau]}'><b>{r.niveau}</b></td><td>{html.escape(r.table)}</td>"
                 f"<td>{NOMS.get(r.corps, r.corps)}</td><td>{html.escape(r.colonne)}</td><td style='text-align:left'>{html.escape(r.constat)}</td></tr>")
    h.append("</table>")
    for (nom, corps), (stats, temoins) in tableaux.items():
        h.append(f"<h2>{html.escape(nom)} · {NOMS[corps]}</h2>")
        if len(temoins):
            h.append("<h3>Sites témoins</h3>" + temoins.to_html(index=False, float_format=lambda x: f"{x:.4g}"))
        h.append("<h3>Statistiques</h3>" + stats.to_html(index=False, float_format=lambda x: f"{x:.4g}", na_rep=""))
    if cartes:
        h.append("<h2>Cartes</h2><p>Moyenne des cellules par case de 0,5° ; gris : pas de cellule ; échelle du 1er au 99e centile.</p>")
        for (nom, k), parc in cartes.items():
            h.append(f"<h3>{html.escape(nom)} · {html.escape(k)}</h3><div class='c'>")
            for corps in ("earth", "mars", "moon"):
                if corps in parc:
                    h.append(f"<img src='data:image/png;base64,{parc[corps]}' alt='{corps} {k}'>")
            h.append("</div>")
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text("\n".join(h), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("module")
    p.add_argument("--dossier", type=Path, help="dossier des résultats (défaut : pretreatment_data/<module>)")
    p.add_argument("--sortie", type=Path, help="rapport HTML (défaut : logs/audit_<module>.html)")
    p.add_argument("--sans-cartes", action="store_true", help="pas de cartes (plus rapide)")
    a = p.parse_args()
    dossier = a.dossier or RACINE / "pretreatment_data" / a.module
    fichiers = sorted(dossier.glob("*.parquet"))
    if not fichiers:
        print(f"Aucun fichier .parquet dans {dossier}"); return 1
    regles = lire_regles(a.module)
    c = Constats()
    tableaux, cartes = {}, (None if a.sans_cartes else {})
    groupes: dict[str, dict] = {}
    for f in fichiers:
        m = MOTIF.match(f.stem)
        if not m:
            print(f"  ignoré (nom inattendu) : {f.name}"); continue
        nom = m["table"] + (m["suffixe"] or "")
        corps, res = m["corps"], int(m["res"])
        print(f"  {f.name}", flush=True)
        t = pd.read_parquet(f)
        groupes.setdefault(nom, {})[corps] = list(t.columns)
        tableaux[(nom, corps)] = auditer_table(nom, corps, res, t, regles, c, cartes)
    for nom, par_corps in groupes.items():
        ref = None
        for corps, cols in par_corps.items():
            if ref is None:
                ref = (corps, cols)
            elif cols != ref[1]:
                diff = sorted(set(cols) ^ set(ref[1]))
                c.ajouter("ERREUR" if diff else "INFO", nom, corps, "", f"colonnes différentes de {NOMS[ref[0]]} : {diff}" if diff
                          else f"mêmes colonnes que {NOMS[ref[0]]} mais dans un autre ordre")
    constats = pd.DataFrame(c.lignes, columns=["niveau", "table", "corps", "colonne", "constat"])
    sortie = a.sortie or RACINE / "logs" / f"audit_{a.module}.html"
    rapport_html(a.module, constats, tableaux, cartes, sortie)
    (sortie.with_suffix(".json")).write_text(json.dumps(c.lignes, ensure_ascii=False, indent=1), encoding="utf-8")
    with pd.option_context("display.width", 250, "display.max_colwidth", 160, "display.max_rows", 500):
        for niveau in ("ERREUR", "ATTENTION", "INFO"):
            s = constats[constats["niveau"] == niveau]
            if len(s):
                print(f"\n{niveau} ({len(s)})")
                print(s.drop(columns="niveau").to_string(index=False))
    print(f"\nRapport : {sortie}")
    return 1 if (constats["niveau"] == "ERREUR").any() else 0


if __name__ == "__main__":
    sys.exit(main())
