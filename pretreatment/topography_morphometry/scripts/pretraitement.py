"""Module « Topographie, morphométrie et cratères » : prétraitement de la Terre, de Mars et de la Lune.

    ./pipeline run topography_morphometry                       # les trois corps, toutes les latitudes
    ./pipeline run topography_morphometry --corps moon mars     # toutes les options : --help

Une ligne par cellule H3 (résolution 5 par défaut ; sur Terre, les cellules qui ont des terres) et par
base de calcul : les pentes et le relief dépendent de la taille du pixel, donc deux corps ne se comparent
qu'à la même base. Base 500 m : les trois corps (celle de Mars) ; base 100 m : Terre et Lune.

  pente_p10 … pente_p90   déciles de la pente (°) : la distribution, pour la distance de Wasserstein
  part_pente_inf_5        part des pixels de pente < 5° (surface où se poser)
  rugosite_rms            écart quadratique de l'altitude à sa moyenne 3 × 3 pixels (m)
  denivele_p5_p95         écart entre les 5e et 95e centiles d'altitude de la cellule (m)
  courbure_moy            courbure moyenne (1/km ; > 0 bombé, < 0 en creux)
  densite_crateres        cratères de 1 km et plus par 1 000 km², sur une fenêtre de ~1 000 à 1 800 km²

Sources
  Terre  Copernicus DEM GLO-90 (ESA, tuiles de 1° sur AWS Open Data), Earth Impact Database (PASSC)
  Mars   MOLA MEGDR 463 m (MGS, mosaïque USGS), base de cratères de Robbins et Hynek (2012)
  Lune   LOLA LDEM 118 m (LRO, mosaïque USGS), base de cratères de Robbins (2018)
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import math
import re
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import h3
import h3.api.basic_int as h3i
import numpy as np
import pandas as pd

ICI = Path(__file__).resolve().parent
RACINE = ICI.parents[2]
sys.path.insert(0, str(RACINE / "scripts"))
from commun import court, reconstruire_duckdb, verifier_espace  # noqa: E402
# Certains serveurs (astrogeology.usgs.gov) refusent l'agent par défaut « Python-urllib » (HTTP 403)
_ouvreur = urllib.request.build_opener()
_ouvreur.addheaders = [("User-Agent", "analogues-pipeline/1.0 (NASA Space Apps Challenge 2026)")]
urllib.request.install_opener(_ouvreur)
MODULE = "topography_morphometry"
SORTIE = RACINE / "pretreatment_data" / MODULE
CACHE = RACINE / "cache" / MODULE
ENTREES = RACINE / "inputs" / MODULE

RAYON = {"earth": 6_371_008.8, "mars": 3_396_190.0, "moon": 1_737_400.0}   # m (sphères des MNT)
NOMS = {"earth": "Terre", "mars": "Mars", "moon": "Lune"}

# --- Terre : Copernicus DEM GLO-90 (3", tuiles de 1° × 1°, pas d'océan), AWS Open Data
URL_COPERNICUS = "https://copernicus-dem-90m.s3.amazonaws.com/{nom}/{nom}.tif"
URL_LISTE_COPERNICUS = "https://copernicus-dem-90m.s3.amazonaws.com/tileList.txt"
# --- Mars et Lune : mosaïques globales USGS (cylindriques simples, -180 à 180°)
URL_MNT = {"mars": "https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif",
           "moon": "https://planetarymaps.usgs.gov/mosaic/Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif"}
SOURCE_M = {"earth": 90.0, "mars": 463.0, "moon": 118.0}                      # pixel de la source, m
# --- Cratères
URL_CRATERES_MARS = ("https://astrogeology.usgs.gov/pygeoapi/collections/mars/robbinsv1/items"
                     "?f=json&limit={n}&offset={debut}")
URL_CRATERES_LUNE = "https://astropedia.astrogeology.usgs.gov/download/Moon/Research/Craters/lunar_crater_database_robbins_2018"
CRATERES_TERRE = ICI.parent / "crateres_terre.csv"
DIAMETRE_MIN_KM = 1.0
FENETRE_KM2 = 1000.0           # la fenêtre de comptage des cratères fait au moins cette surface

DECILES = [10, 20, 30, 40, 50, 60, 70, 80, 90]
PENTE_PLATE = 5.0              # °
PIXELS_STATS = 2000            # au-delà de ~2 × ce nombre de pixels par cellule, on en lit un sur N²
COLONNES = (["body", "resolution", "h3", "base_m", "base_effective_m", "resolution_source_m"]
            + [f"pente_p{d}" for d in DECILES]
            + ["pente_moy", "part_pente_inf_5", "rugosite_rms", "denivele_p5_p95", "courbure_moy",
               "courbure_abs_moy", "densite_crateres", "n_pixels", "couverture", "fiabilite"])

SITES = {
    "earth": {"Meteor Crater": (35.027, -111.022), "Haughton": (75.38, -89.68), "Atacama": (-24.5, -69.25),
              "Death Valley": (36.46, -116.87), "Everest": (27.99, 86.93), "Pays-Bas (polders)": (52.4, 5.3),
              "Montréal": (45.5, -73.57)},
    "mars": {"Gale": (-4.59, 137.44), "Jezero": (18.44, 77.45), "Olympus Mons": (18.65, -133.8),
             "Valles Marineris": (-13.9, -59.2), "Utopia Planitia": (46.7, 117.5), "Hellas (fond)": (-42.4, 70.5),
             "Calotte nord": (87.0, 0.0)},
    "moon": {"Apollo 11 (mare)": (0.674, 23.473), "Apollo 16 (hautes terres)": (-8.973, 15.5),
             "Mare Imbrium": (32.8, -15.6), "Tycho": (-43.31, -11.36), "Shackleton": (-89.67, 129.78)},
}


def options() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--corps", nargs="+", choices=("earth", "mars", "moon"), default=["earth", "mars", "moon"])
    p.add_argument("--resolution", type=int, default=5, help="résolution H3 (défaut : 5)")
    p.add_argument("--bases", nargs="+", type=int, default=[500, 100],
                   help="bases de calcul en mètres (défaut : 500 100 ; Mars n'a que 500)")
    p.add_argument("--crateres-seulement", action="store_true",
                   help="recalculer seulement densite_crateres dans les résultats déjà écrits")
    g = p.add_argument_group("Terre")
    g.add_argument("--zone", nargs=4, type=float, metavar=("OUEST", "SUD", "EST", "NORD"),
                   help="ne traiter que les tuiles de cette boîte (degrés) ; ne télécharge qu'elles")
    g.add_argument("--telechargements", type=int, default=6, help="tuiles téléchargées en parallèle (défaut : 6)")
    g = p.add_argument_group("Mars et Lune")
    g.add_argument("--mnt-mars", type=Path, default=ENTREES / "mnt_mars",
                   help=f"MNT de Mars (fichier .tif ou dossier) ; sinon téléchargé (défaut : inputs/{MODULE}/mnt_mars)")
    g.add_argument("--mnt-lune", type=Path, default=ENTREES / "mnt_lune",
                   help=f"MNT de la Lune (fichier .tif ou dossier) ; sinon téléchargé (défaut : inputs/{MODULE}/mnt_lune)")
    g.add_argument("--echelle-lune", type=float, default=None,
                   help="mètres par unité du MNT lunaire (défaut : celle du fichier, sinon 0,5 pour un LDEM en int16)")
    g.add_argument("--crateres-mars", type=Path, default=ENTREES / "crateres_mars",
                   help=f"catalogue de cratères de Mars (.csv/.tsv ou dossier) (défaut : inputs/{MODULE}/crateres_mars)")
    g.add_argument("--crateres-lune", type=Path, default=ENTREES / "crateres_lune",
                   help=f"catalogue de cratères de la Lune (.csv ou dossier) (défaut : inputs/{MODULE}/crateres_lune)")
    return p.parse_args()


# ------------------------------------------------------------------ téléchargements
def telecharger(url: str, cible: Path, bavard: bool = True, essais: int = 3) -> bool:
    """Téléchargement avec reprise (.part) : utile pour les MNT de plusieurs Go."""
    if cible.is_file() and cible.stat().st_size > 0:
        return True
    cible.parent.mkdir(parents=True, exist_ok=True)
    partiel = cible.with_name(cible.name + ".part")
    for essai in range(essais):
        deja = partiel.stat().st_size if partiel.is_file() else 0
        req = urllib.request.Request(url, headers={"Range": f"bytes={deja}-"} if deja else {})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                if deja and r.status != 206:              # le serveur ne reprend pas : recommencer
                    deja = 0
                total = deja + int(r.headers.get("Content-Length") or 0)
                if bavard:
                    print(f"  téléchargement de {cible.name}" + (f" ({total / 1e9:.2f} Go)" if total > 2e8 else "")
                          + (f", reprise à {deja / 1e9:.2f} Go" if deja else "") + "...", flush=True)
                suivant = deja + 5e8
                with open(partiel, "ab" if deja else "wb") as f:
                    while bloc := r.read(1 << 20):
                        f.write(bloc)
                        deja += len(bloc)
                        if bavard and total > 2e9 and deja >= suivant:
                            print(f"    {deja / 1e9:.1f} / {total / 1e9:.1f} Go", flush=True)
                            suivant += 5e8
            partiel.replace(cible)
            return True
        except OSError as e:
            if getattr(e, "code", None) == 404:
                print(f"  {cible.name} : introuvable (404)")
                return False
            if essai == essais - 1:
                print(f"  {cible.name} : téléchargement impossible ({e})")
            time.sleep(3 * (essai + 1))
    return False


def liberer() -> None:
    """Rend au système la mémoire libérée (glibc garde sinon les morceaux des grands tableaux temporaires)."""
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


# ------------------------------------------------------------------ géométrie H3
def aire_cellule_m2(res: int, rayon: float) -> float:
    return h3.average_hexagon_area(res, "km^2") * 1e6 * (rayon / 6_371_007.18) ** 2


def boites(cellules: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Latitude minimale, longitude maximale et « cas spécial » (antiméridien ou pôle) de chaque cellule."""
    lat_min = np.empty(len(cellules)); lon_max = np.empty(len(cellules)); special = np.zeros(len(cellules), bool)
    for i, c in enumerate(cellules.tolist()):
        b = np.asarray(h3i.cell_to_boundary(c))
        lat_min[i] = b[:, 0].min(); lon_max[i] = b[:, 1].max()
        special[i] = b[:, 1].max() - b[:, 1].min() > 180
    return lat_min, lon_max, special


class Accumulateur:
    """Garde les pixels des cellules encore « ouvertes » et calcule les statistiques exactes d'une cellule
    dès que tous ses pixels sont passés (on parcourt le MNT du nord au sud)."""

    def __init__(self, corps: str, res: int, base: int, base_eff: float, bloc_m: float):
        self.corps, self.res, self.base, self.base_eff = corps, res, base, base_eff
        self.rayon = RAYON[corps]
        self.marge = math.degrees(3 * max(bloc_m, base_eff) / self.rayon) + 1e-3
        self.morceaux: list[dict] = []          # pixels avec une altitude
        self.blocs: list[tuple] = []            # (cellule, surface) de chaque bloc lu, données ou non
        self.taille = 0
        self.resultats: list[pd.DataFrame] = []
        self.poles = {h3i.latlng_to_cell(90.0, 0.0, res): "nord", h3i.latlng_to_cell(-90.0, 0.0, res): "sud"}

    def ajouter(self, d: dict, cel_blocs: np.ndarray, aire_blocs: np.ndarray) -> None:
        self.blocs.append((cel_blocs.ravel(), aire_blocs.ravel()))
        ok = np.isfinite(d["alt"])
        if ok.any():
            d = {k: v[ok] for k, v in d.items()}
            self.morceaux.append(d)
            self.taille += len(d["cell"])

    def fermer(self, sud: float | None, est: float | None = None) -> None:
        """Calcule les cellules entièrement au nord de `sud` (et à l'ouest de `est`). sud=None : toutes."""
        if not self.blocs:
            return
        bc = np.concatenate([b[0] for b in self.blocs]); ba = np.concatenate([b[1] for b in self.blocs])
        tout = ({k: np.concatenate([m[k] for m in self.morceaux]) for k in self.morceaux[0]}
                if self.morceaux else None)
        uniques = np.unique(bc)
        if sud is None:
            fermees = uniques
        else:
            lat_min, lon_max, special = boites(uniques)
            for c, quoi in self.poles.items():
                j = np.searchsorted(uniques, c)
                if j < len(uniques) and uniques[j] == c:
                    special[j] = True
                    if quoi == "sud":
                        lat_min[j] = -90.0
            ok = lat_min > sud + self.marge
            if est is not None:
                ok &= ~special & (lon_max < est - self.marge)
            fermees = uniques[ok]
        selb = np.isin(bc, fermees)
        self.blocs = [(bc[~selb], ba[~selb])] if (~selb).any() else []
        if tout is None:
            return
        sel = np.isin(tout["cell"], fermees)
        if sel.any():
            self.resultats.append(statistiques({k: v[sel] for k, v in tout.items()}, bc[selb], ba[selb], self))
        reste = {k: v[~sel] for k, v in tout.items()}
        self.morceaux = [reste] if len(reste["cell"]) else []
        self.taille = len(reste["cell"])
        del tout
        liberer()

    def table(self) -> pd.DataFrame:
        self.fermer(None)
        if not self.resultats:
            return pd.DataFrame(columns=COLONNES)
        t = pd.concat(self.resultats, ignore_index=True)
        self.resultats = []
        t.insert(2, "h3", [h3i.int_to_str(c) for c in t.pop("h3i").tolist()])
        doublons = int(t["h3"].duplicated().sum())
        if doublons:
            print(f"  attention : {doublons} cellules calculées en deux fois ; on garde la plus complète")
            t = t.sort_values("n_pixels", ascending=False).drop_duplicates("h3").sort_values("h3")
        return t.sort_values("h3", ignore_index=True)


def quantiles_groupes(g: np.ndarray, x: np.ndarray, n: int, qs, decalage: float, largeur: float) -> np.ndarray:
    """Quantiles (interpolation linéaire, comme numpy) de x dans chaque groupe g ∈ [0, n) : un seul tri."""
    cle = g.astype(np.float64) * largeur + (np.clip(x.astype(np.float64), decalage, decalage + largeur * 0.999) - decalage)
    cle.sort()
    gs = np.minimum(np.floor(cle / largeur).astype(np.int64), n - 1)
    v = cle - gs * largeur + decalage
    nb = np.bincount(gs, minlength=n)
    debut = np.concatenate([[0], np.cumsum(nb)[:-1]])
    sortie = np.full((len(qs), n), np.nan)
    a = nb > 0
    for i, q in enumerate(qs):
        pos = debut[a] + q / 100 * (nb[a] - 1)
        bas = np.floor(pos).astype(np.int64)
        haut = np.minimum(bas + 1, debut[a] + nb[a] - 1)
        w = pos - bas
        sortie[i, a] = v[bas] * (1 - w) + v[haut] * w
    return sortie


def statistiques(d: dict, cel_blocs: np.ndarray, aire_blocs: np.ndarray, acc: Accumulateur) -> pd.DataFrame:
    u, g = np.unique(d["cell"], return_inverse=True)
    n = len(u)
    t = {"body": acc.corps, "resolution": acc.res, "h3i": u,
         "base_m": acc.base, "base_effective_m": round(acc.base_eff, 1), "resolution_source_m": SOURCE_M[acc.corps]}
    p = d["pente"]; vp = np.isfinite(p)
    npente = np.bincount(g[vp], minlength=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        q = quantiles_groupes(g[vp], p[vp], n, DECILES, 0.0, 128.0)
        for i, dec in enumerate(DECILES):
            t[f"pente_p{dec}"] = q[i]
        t["pente_moy"] = np.bincount(g[vp], p[vp], minlength=n) / npente
        t["part_pente_inf_5"] = np.bincount(g[vp], (p[vp] < PENTE_PLATE).astype(float), minlength=n) / npente
        r = d["res2"]; vr = np.isfinite(r)
        t["rugosite_rms"] = np.sqrt(np.bincount(g[vr], r[vr], minlength=n) / np.bincount(g[vr], minlength=n))
        z = quantiles_groupes(g, d["alt"], n, [5, 95], -32768.0, 65536.0)
        t["denivele_p5_p95"] = z[1] - z[0]
        c = d["courb"]; vc = np.isfinite(c)
        nc = np.bincount(g[vc], minlength=n)
        t["courbure_moy"] = np.bincount(g[vc], c[vc], minlength=n) / nc
        t["courbure_abs_moy"] = np.bincount(g[vc], np.abs(c[vc]), minlength=n) / nc
    t["densite_crateres"] = np.nan
    t["n_pixels"] = npente
    # couverture : surface des pixels qui ont une altitude / surface de tous les pixels lus de la cellule
    aire = np.bincount(g, d["aire"], minlength=n)
    j = np.searchsorted(u, cel_blocs)
    ok = (j < n) & (u[np.minimum(j, n - 1)] == cel_blocs)
    lue = np.bincount(j[ok], aire_blocs[ok], minlength=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        t["couverture"] = np.clip(aire / lue, 0, 1)
    t["fiabilite"] = t["couverture"]
    return pd.DataFrame(t)


# ------------------------------------------------------------------ calcul sur une bande du MNT
def diviseurs_proches(n: int, cibles: np.ndarray) -> np.ndarray:
    """Pour chaque cible, le diviseur de n le plus proche (en rapport) : sur une grille globale, des blocs
    de colonnes tous de même largeur, y compris au raccord -180/180°."""
    ds = np.array([d for d in range(1, n + 1) if n % d == 0], dtype=float)
    c = np.clip(np.nan_to_num(cibles, nan=n, posinf=n), 1.0, n)
    return ds[np.abs(np.log(ds)[None, :] - np.log(c)[:, None]).argmin(axis=1)].astype(int)


def traiter_bande(z: np.ndarray, lat: np.ndarray, lon: np.ndarray, halo_haut: int, halo_bas: int,
                  fy: int, base_eff: float, bloc_m: float, pas: int, acc: Accumulateur, global_: bool) -> None:
    """z : altitudes (m, NaN = pas de donnée), lignes du nord au sud, centres lat (lignes) et lon (colonnes),
    réguliers. halo_haut/halo_bas : lignes natives au-dessus/au-dessous qui servent de voisines seulement.
    Les pixels sont regroupés par fy lignes, puis, à chaque latitude, par fx colonnes pour rester carrés
    (~ base_eff de côté) jusqu'aux pôles."""
    R = acc.rayon
    nr, nc = z.shape
    nra = nr // fy
    z = z[: nra * fy]
    v = np.isfinite(z)
    cnt = v.reshape(nra, fy, nc).sum(axis=1).astype(np.float32)
    som = np.where(v, z, 0).reshape(nra, fy, nc).sum(axis=1, dtype=np.float64)
    lat_a = lat[: nra * fy].reshape(nra, fy).mean(axis=1)
    ha, hb = halo_haut // fy, halo_bas // fy
    dlat = abs(lat[1] - lat[0]) if len(lat) > 1 else 1.0
    dlon = float(lon[1] - lon[0])
    dy = R * math.radians(dlat) * fy
    aire_pix = R ** 2 * math.radians(dlat) * math.radians(dlon)        # × cos(lat), pixel natif
    cos_a = np.cos(np.radians(lat_a))
    with np.errstate(divide="ignore"):
        cible = base_eff / np.maximum(R * cos_a * math.radians(dlon), 1e-9)
    if global_:
        fx = diviseurs_proches(nc, cible)
    else:
        fx = np.clip(np.rint(cible), 1, nc).astype(int)
    sorties = np.arange(ha, nra - hb)
    if len(sorties) == 0:
        return
    # groupes de lignes de sortie consécutives qui ont le même fx
    coupures = np.flatnonzero(np.diff(fx[sorties])) + 1
    for groupe in np.split(sorties, coupures):
        r0, r1 = int(groupe[0]), int(groupe[-1])
        k = int(fx[r0])
        s0, s1 = max(r0 - 1, 0), min(r1 + 1, nra - 1)              # avec une ligne voisine de chaque côté
        debuts = np.arange(0, nc, k)
        S = np.add.reduceat(som[s0:s1 + 1], debuts, axis=1)
        C = np.add.reduceat(cnt[s0:s1 + 1], debuts, axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            G = (S / C).astype(np.float64)
        G[C == 0] = np.nan
        lon_b = np.add.reduceat(lon, debuts) / np.diff(np.append(debuts, nc))
        lat_g = lat_a[s0:s1 + 1]
        nb = G.shape[1]
        o, m = r0 - s0, r1 - r0 + 1                                   # lignes de sortie dans G : o .. o+m-1
        Gs = G[o:o + m]
        cosg = np.cos(np.radians(lat_g[o:o + m]))[:, None]
        # --- dérivées en x (est), en mètres
        if nb >= 3:
            if global_:
                Ge, Gw = np.roll(Gs, -1, axis=1), np.roll(Gs, 1, axis=1)
                ecart = np.full(nb, 2 * math.radians(dlon * k))
            else:
                Ge = np.concatenate([Gs[:, 1:], Gs[:, -1:]], axis=1)
                Gw = np.concatenate([Gs[:, :1], Gs[:, :-1]], axis=1)
                le = np.append(lon_b[1:], lon_b[-1]); lw = np.insert(lon_b[:-1], 0, lon_b[0])
                ecart = np.radians(le - lw)
            hx = R * cosg * ecart[None, :]
            with np.errstate(invalid="ignore", divide="ignore"):
                dzdx = (Ge - Gw) / hx
                d2x = (Ge - 2 * Gs + Gw) / (hx / 2) ** 2
            if not global_:
                d2x[:, [0, -1]] = np.nan
        else:                                                         # au pôle : une seule colonne
            Ge = Gw = Gs
            dzdx = np.zeros_like(Gs); d2x = np.zeros_like(Gs)
        # --- dérivées en y (nord)
        idx = np.arange(o, o + m)
        nord = np.where(idx - 1 >= 0, idx - 1, idx)
        sud = np.where(idx + 1 < G.shape[0], idx + 1, idx)
        Gn, Gsu = G[nord], G[sud]
        with np.errstate(invalid="ignore", divide="ignore"):
            dzdy = (Gn - Gsu) / (dy * (sud - nord))[:, None]
            d2y = (Gn - 2 * Gs + Gsu) / dy ** 2
        d2y[(sud == idx) | (nord == idx)] = np.nan
        pente = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
        courb = -(d2x + d2y) * 1000.0                                 # 1/km, > 0 bombé
        # --- rugosité : écart à la moyenne 3 × 3
        if nb >= 3:
            Gne, Gnw = np.roll(Gn, -1, axis=1), np.roll(Gn, 1, axis=1)
            Gse, Gsw = np.roll(Gsu, -1, axis=1), np.roll(Gsu, 1, axis=1)
            moy = (Gs + Ge + Gw + Gn + Gsu + Gne + Gnw + Gse + Gsw) / 9
            res2 = (Gs - moy) ** 2
            if not global_:
                res2[:, [0, -1]] = np.nan
            res2[(sud == idx) | (nord == idx)] = np.nan
        else:
            res2 = np.full_like(Gs, np.nan)
        # --- cellule H3 de chaque pixel, par blocs d'environ bloc_m de côté
        by = max(1, int(round(bloc_m / dy)))
        dx_moy = R * float(np.mean(cosg)) * math.radians(dlon * k)
        bx = max(1, int(round(bloc_m / max(dx_moy, 1e-6))))
        lat_r = lat_g[o:o + m]
        lat_blocs = np.add.reduceat(lat_r, np.arange(0, m, by)) / np.diff(np.append(np.arange(0, m, by), m))
        lon_blocs = np.add.reduceat(lon_b, np.arange(0, nb, bx)) / np.diff(np.append(np.arange(0, nb, bx), nb))
        lon_blocs = (lon_blocs + 180) % 360 - 180
        cel_blocs = np.empty((len(lat_blocs), len(lon_blocs)), dtype=np.uint64)
        lons = lon_blocs.tolist()
        for i, a in enumerate(lat_blocs.tolist()):
            cel_blocs[i] = np.fromiter((h3i.latlng_to_cell(a, b, acc.res) for b in lons), np.uint64, len(lons))
        cel = np.repeat(np.repeat(cel_blocs, by, axis=0)[:m], bx, axis=1)[:, :nb]
        aire = C[o:o + m] * aire_pix * cosg
        largeurs = np.diff(np.append(debuts, nc))
        aire_lue = (fy * aire_pix) * cosg * largeurs[None, :]
        aire_blocs = np.add.reduceat(np.add.reduceat(aire_lue, np.arange(0, m, by), axis=0), np.arange(0, nb, bx), axis=1)
        # --- un pixel sur pas² pour les statistiques (cellules de plusieurs dizaines de milliers de pixels)
        sl = (slice(pas // 2, None, pas), slice(pas // 2, None, pas))
        acc.ajouter({"cell": cel[sl].ravel(), "pente": pente[sl].ravel().astype(np.float32),
                     "alt": Gs[sl].ravel().astype(np.float32), "res2": res2[sl].ravel().astype(np.float32),
                     "courb": courb[sl].ravel().astype(np.float32),
                     "aire": (aire[sl] * pas * pas).ravel().astype(np.float32)}, cel_blocs, aire_blocs)


def parametres_base(corps: str, res: int, base: int, dlat_deg: float) -> tuple[int, float, float, int]:
    """fy (lignes natives par pixel de base), côté effectif (m), taille des blocs d'affectation (m), pas."""
    R = RAYON[corps]
    dy_natif = R * math.radians(dlat_deg)
    fy = max(1, int(round(base / dy_natif)))
    base_eff = fy * dy_natif
    aire_c = aire_cellule_m2(res, R)
    bloc_m = math.sqrt(aire_c) / 8
    pas = max(1, int(math.sqrt(aire_c / base_eff ** 2 / PIXELS_STATS)))
    return fy, base_eff, bloc_m, pas


# ------------------------------------------------------------------ Mars et Lune : MNT global
def fichier_mnt(corps: str, chemin: Path) -> Path | None:
    if chemin.is_file():
        return chemin
    if chemin.is_dir():
        tifs = sorted(chemin.glob("*.tif")) + sorted(chemin.glob("*.tiff"))
        if tifs:
            return max(tifs, key=lambda f: f.stat().st_size)
    cible = CACHE / URL_MNT[corps].rsplit("/", 1)[1]
    if not cible.is_file():
        verifier_espace(CACHE, {"mars": 3, "moon": 10}[corps],
                        f"le MNT de {NOMS[corps]} ({'2' if corps == 'mars' else '8'} Go) — ou le mettre sur un autre "
                        f"disque et passer --mnt-{'mars' if corps == 'mars' else 'lune'} /chemin")
    print(f"{NOMS[corps]} : MNT absent de {chemin}, téléchargement depuis l'USGS (une seule fois)")
    return cible if telecharger(URL_MNT[corps], cible) else None


def lire_geometrie(src, corps: str):
    """Centres des lignes (lat) et des colonnes (lon), en degrés, d'une mosaïque globale."""
    tr = src.transform
    W, H = src.width, src.height
    x = tr.c + (np.arange(W) + 0.5) * tr.a
    y = tr.f + (np.arange(H) + 0.5) * tr.e
    if src.crs is not None and src.crs.is_geographic:
        lon, lat = x, y
    else:                                                     # cylindrique simple en mètres : x = Rλ, y = Rφ
        R = (W * abs(tr.a)) / (2 * math.pi)
        if abs(R - RAYON[corps]) / RAYON[corps] > 0.02:
            sys.exit(f"{NOMS[corps]} : le MNT ne couvre pas les 360° (rayon déduit {R:.0f} m) ; il faut une mosaïque globale")
        lon, lat = np.degrees(x / R), np.degrees(y / R)
    if abs((lon[-1] - lon[0]) + (lon[1] - lon[0]) - 360) > 0.01 or abs(lat[0] - lat[-1] + abs(lat[1] - lat[0]) - 180) > 0.01:
        sys.exit(f"{NOMS[corps]} : le MNT doit couvrir tout le corps (-180 à 180°, -90 à 90°)")
    return lat, lon


def mnt_global(corps: str, args) -> None:
    import rasterio
    chemin = fichier_mnt(corps, args.mnt_mars if corps == "mars" else args.mnt_lune)
    if chemin is None:
        print(f"{NOMS[corps]} : pas de MNT ; voir le README pour le télécharger à la main")
        return
    crat = crateres(corps, args)
    with rasterio.open(chemin) as src:
        lat, lon = lire_geometrie(src, corps)
        echelle, decalage = float(src.scales[0] or 1.0), float(src.offsets[0] or 0.0)
        if corps == "moon":
            if args.echelle_lune is not None:
                echelle = args.echelle_lune
            elif echelle == 1.0 and src.dtypes[0] == "int16":
                echelle = 0.5
                print("Lune : le fichier n'indique pas d'échelle ; LDEM en int16 = demi-mètres, échelle 0,5")
        nodata = src.nodata
        H, W = src.height, src.width
        dlat = abs(lat[1] - lat[0])
        print(f"{NOMS[corps]} : {chemin.name}, {W} × {H} pixels de {RAYON[corps] * math.radians(dlat):.0f} m, "
              f"échelle {echelle:g} m")
        for base in sorted(set(args.bases), reverse=True):
            if base < SOURCE_M[corps] * 0.75:
                print(f"{NOMS[corps]} : base {base} m plus fine que la source ({SOURCE_M[corps]:.0f} m), ignorée")
                continue
            t0 = time.time()
            fy, base_eff, bloc_m, pas = parametres_base(corps, args.resolution, base, dlat)
            acc = Accumulateur(corps, args.resolution, base, base_eff, bloc_m)
            hauteur = max(fy, int(4e6 / W) // fy * fy)
            print(f"  base {base} m : pixels de {base_eff:.0f} m, bandes de {hauteur} lignes", flush=True)
            prochain = 0
            for r0 in range(0, H - H % fy, hauteur):
                r1 = min(r0 + hauteur, H - H % fy)
                a0, a1 = max(r0 - fy, 0), min(r1 + fy, H - H % fy)
                z = src.read(1, window=((a0, a1), (0, W))).astype(np.float64)
                if nodata is not None:
                    z[z == nodata] = np.nan
                z = z * echelle + decalage
                traiter_bande(z, lat[a0:a1], lon, r0 - a0, a1 - r1, fy, base_eff, bloc_m, pas, acc, True)
                acc.fermer(float(lat[r1 - 1] - dlat / 2))
                if r0 / H >= prochain:
                    print(f"    {lat[r0]:+6.1f}°  ({(time.time() - t0) / 60:.1f} min)", flush=True)
                    prochain += 0.1
            t = acc.table()
            t["densite_crateres"] = densite_crateres(t["h3"].to_numpy(), crat, corps, args.resolution)
            ecrire(corps, args.resolution, base, t, sources(corps, chemin.name, crat))
            print(f"  base {base} m : {(time.time() - t0) / 60:.1f} min")


# ------------------------------------------------------------------ Terre : tuiles Copernicus
def tuiles_copernicus(zone) -> list[tuple[str, int, int]]:
    liste = CACHE / "copernicus_tileList.txt"
    if not telecharger(URL_LISTE_COPERNICUS, liste, bavard=False):
        sys.exit("Terre : liste des tuiles Copernicus inaccessible (réseau ?)")
    tuiles = []
    for nom in liste.read_text().split():
        m = re.search(r"_([NS])(\d+)_\d+_([EW])(\d+)_\d+_DEM", nom)
        if not m:
            continue
        la = int(m[2]) * (1 if m[1] == "N" else -1)
        lo = int(m[4]) * (1 if m[3] == "E" else -1)
        if zone and not (lo + 1 > zone[0] and lo < zone[2] and la + 1 > zone[1] and la < zone[3]):
            continue
        tuiles.append((nom, la, lo))
    return sorted(tuiles, key=lambda t: (-t[1], t[2]))               # du nord au sud, d'ouest en est


def terre(args) -> None:
    import rasterio
    verifier_espace(CACHE, 1, "les tuiles Copernicus (effacées au fur et à mesure)")
    tuiles = tuiles_copernicus(args.zone)
    crat = crateres("earth", args)
    bases = sorted({b for b in args.bases if b >= SOURCE_M["earth"] * 0.75}, reverse=True)
    if not bases:
        return
    print(f"Terre : {len(tuiles):,} tuiles Copernicus GLO-90 à lire (~2 à 4 Mo chacune, effacées après lecture), "
          f"bases {', '.join(map(str, bases))} m", flush=True)
    dossier = CACHE / "copernicus"
    accs, params = {}, {}
    dlat = 3 / 3600
    for b in bases:
        params[b] = parametres_base("earth", args.resolution, b, dlat)
        accs[b] = Accumulateur("earth", args.resolution, b, params[b][1], params[b][2])
    t0, manquantes = time.time(), []

    def charger(t):
        nom = t[0]
        f = dossier / f"{nom}.tif"
        return t, (f if telecharger(URL_COPERNICUS.format(nom=nom), f, bavard=False) else None)

    rang_precedent, prochain = None, 0
    n_par = max(1, args.telechargements)
    with cf.ThreadPoolExecutor(n_par) as pool:
        en_cours = [pool.submit(charger, t) for t in tuiles[: 2 * n_par]]     # pas plus de 2 × n tuiles d'avance
        for i in range(len(tuiles)):
            t, f = en_cours.pop(0).result()
            if i + 2 * n_par < len(tuiles):
                en_cours.append(pool.submit(charger, tuiles[i + 2 * n_par]))
            nom, la, lo = t
            if rang_precedent is not None and la != rang_precedent:
                for acc in accs.values():
                    acc.fermer(float(rang_precedent))
            rang_precedent = la
            if f is None:
                manquantes.append(nom)
                continue
            try:
                with rasterio.open(f) as src:
                    z = src.read(1).astype(np.float64)
                    if src.nodata is not None:
                        z[z == src.nodata] = np.nan
                    tr = src.transform
                    lat_t = tr.f + (np.arange(src.height) + 0.5) * tr.e
                    lon_t = tr.c + (np.arange(src.width) + 0.5) * tr.a
            except Exception as e:                                         # fichier abîmé : on le signale
                print(f"  {nom} : illisible ({e})")
                manquantes.append(nom)
                f.unlink(missing_ok=True)
                continue
            f.unlink(missing_ok=True)
            z[z == 0] = np.nan                                             # mer
            for b, acc in accs.items():
                fy, base_eff, bloc_m, pas = params[b]
                traiter_bande(z, lat_t, lon_t, 0, 0, fy, base_eff, bloc_m, pas, acc, False)
                if acc.taille > 5_000_000:
                    acc.fermer(float(la), float(lo + 1))
            if i / len(tuiles) >= prochain:
                print(f"  {i:,}/{len(tuiles):,} tuiles, latitude {la:+d}°  ({(time.time() - t0) / 60:.1f} min)", flush=True)
                prochain += 0.05
    if manquantes:
        print(f"  {len(manquantes)} tuiles non lues : {', '.join(manquantes[:5])}{' …' if len(manquantes) > 5 else ''}"
              " ; relancer avec --zone sur ces tuiles")
    lues = {(la, lo) for nom, la, lo in tuiles if nom not in set(manquantes)}
    for b, acc in accs.items():
        t = acc.table()
        # la mer n'a pas de tuile : la part de la cellule hors des tuiles lues compte comme sans donnée
        t["couverture"] = t["couverture"] * part_dans_tuiles(t["h3"].to_numpy(), lues)
        t["fiabilite"] = t["couverture"]
        t["densite_crateres"] = densite_crateres(t["h3"].to_numpy(), crat, "earth", args.resolution)
        ecrire("earth", args.resolution, b, t, sources("earth", "Copernicus DEM GLO-90", crat))
    print(f"Terre : {(time.time() - t0) / 60:.1f} min")


def part_dans_tuiles(cellules: np.ndarray, lues: set) -> np.ndarray:
    """Part de chaque cellule dans les tuiles lues, estimée en 7 points (centre et sommets rapprochés)."""
    part = np.empty(len(cellules))
    for i, c in enumerate(cellules.tolist()):
        clat, clon = h3.cell_to_latlng(c)
        pts = [(clat, clon)] + [(clat + 0.9 * (a - clat), clon + 0.9 * ((b - clon + 180) % 360 - 180))
                                for a, b in h3.cell_to_boundary(c)]
        part[i] = np.mean([(math.floor(a), math.floor((b + 180) % 360 - 180)) in lues for a, b in pts])
    return part


# ------------------------------------------------------------------ cratères
def lire_catalogue(f: Path) -> pd.DataFrame:
    """Latitude, longitude et diamètre (km) d'un catalogue : reconnaît les colonnes de Robbins (Mars 2012 :
    LATITUDE_CIRCLE_IMAGE… ; Lune 2018 : LAT_CIRC_IMG…), du service USGS (lat, lon_e, diamkm) et du CSV de
    la Terre."""
    with open(f, encoding="utf-8", errors="replace") as h:
        entete = next(l for l in h if not l.startswith("#"))
    sep = "\t" if entete.count("\t") > entete.count(",") else ","
    t = pd.read_csv(f, sep=sep, comment="#", low_memory=False)
    noms = {c.lower().strip(): c for c in t.columns}

    def choisir(preferes, motif):
        for p in preferes:
            if p in noms:
                return noms[p]
        for k, c in noms.items():
            if re.search(motif, k):
                return c
        sys.exit(f"{f.name} : colonne {motif} introuvable parmi {list(t.columns)[:12]}")
    cla = choisir(["lat_circ_img", "latitude_circle_image", "lat", "latitude"], r"^lat")
    clo = choisir(["lon_circ_img", "longitude_circle_image", "lon_e", "lon", "longitude"], r"^lon")
    cdi = choisir(["diam_circ_img", "diam_circle_image", "diamkm", "diametre_km", "diameter_km"], r"diam")
    print(f"  {f.name} : {len(t):,} cratères (colonnes {cla}, {clo}, {cdi})")
    lon = (pd.to_numeric(t[clo], errors="coerce") + 180) % 360 - 180
    return pd.DataFrame({"lat": pd.to_numeric(t[cla], errors="coerce"), "lon": lon,
                         "diam_km": pd.to_numeric(t[cdi], errors="coerce")}).dropna()


def catalogue_local(chemin: Path) -> Path | None:
    if chemin.is_file():
        return chemin
    if chemin.is_dir():
        fs = [f for ext in ("*.csv", "*.tsv", "*.txt") for f in chemin.glob(ext)]
        if fs:
            return max(fs, key=lambda f: f.stat().st_size)
    return None


def crateres(corps: str, args) -> pd.DataFrame | None:
    if corps == "earth":
        return lire_catalogue(CRATERES_TERRE)
    f = catalogue_local(args.crateres_mars if corps == "mars" else args.crateres_lune)
    if f is None:
        f = (telecharger_crateres_mars if corps == "mars" else telecharger_crateres_lune)()
    if f is None:
        print(f"{NOMS[corps]} : pas de catalogue de cratères, densite_crateres sera vide (voir le README)")
        return None
    return lire_catalogue(f)


def telecharger_crateres_mars() -> Path | None:
    cible = CACHE / "crateres_mars_robbins2012.csv"
    if cible.is_file():
        return cible
    print("Mars : téléchargement du catalogue de Robbins et Hynek (2012), ~384 000 cratères...", flush=True)
    lignes, debut, n, premier = [], 0, 10000, None
    while debut < 2_000_000:
        try:
            with urllib.request.urlopen(URL_CRATERES_MARS.format(n=n, debut=debut), timeout=300) as r:
                feats = json.load(r).get("features", [])
        except (OSError, ValueError) as e:
            print(f"  service USGS inaccessible ({e})")
            return None
        if not feats or (lignes and feats[0].get("id") is not None and feats[0].get("id") == premier):
            break                                                     # fin, ou serveur qui ignore offset
        premier = feats[0].get("id")
        for ft in feats:
            pr = ft.get("properties") or {}
            co = (ft.get("geometry") or {}).get("coordinates") or [None, None]
            lignes.append((pr.get("lat", co[1]), pr.get("lon_e", co[0]), pr.get("diamkm")))
        debut += len(feats)
        if debut % 50000 < len(feats):
            print(f"  {debut:,} cratères", flush=True)
    if not lignes:
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(lignes, columns=["lat", "lon_e", "diamkm"]).to_csv(cible, index=False)
    return cible


def telecharger_crateres_lune() -> Path | None:
    cible = CACHE / "crateres_lune_robbins2018.csv"
    if cible.is_file():
        return cible
    brut = CACHE / "lunar_crater_database_robbins_2018.telechargement"
    print("Lune : téléchargement du catalogue de Robbins (2018), ~1,3 million de cratères (~90 Mo)...", flush=True)
    if not telecharger(URL_CRATERES_LUNE, brut):
        return None
    if zipfile.is_zipfile(brut):
        with zipfile.ZipFile(brut) as z:
            csvs = [i for i in z.infolist() if i.filename.lower().endswith((".csv", ".tsv"))]
            if not csvs:
                print(f"  l'archive ne contient pas de CSV : {[i.filename for i in z.infolist()][:10]}")
                return None
            with z.open(max(csvs, key=lambda i: i.file_size)) as s, open(cible, "wb") as d:
                d.write(s.read())
    else:
        debut = brut.read_bytes()[:200].lower()
        if b"<html" in debut or b"<!doctype" in debut:
            print("  le serveur a renvoyé une page web, pas le catalogue : le télécharger à la main (README)")
            brut.unlink()
            return None
        brut.replace(cible)
    brut.unlink(missing_ok=True)
    return cible


def densite_crateres(cellules: np.ndarray, crat: pd.DataFrame | None, corps: str, res: int) -> np.ndarray:
    """Cratères de diamètre >= 1 km par 1 000 km², comptés sur la cellule et ses voisines jusqu'à l'anneau k,
    k choisi pour que la fenêtre fasse au moins 1 000 km² (Terre k = 1, Mars k = 2, Lune k = 4 à la rés. 5)."""
    if crat is None or len(cellules) == 0:
        return np.full(len(cellules), np.nan)
    aire_km2 = aire_cellule_m2(res, RAYON[corps]) / 1e6
    k = 0
    while (3 * k * k + 3 * k + 1) * aire_km2 < FENETRE_KM2:
        k += 1
    c = crat[crat["diam_km"] >= DIAMETRE_MIN_KM]
    cel_c = np.array([h3i.latlng_to_cell(float(a), float(b), res) for a, b in zip(c["lat"], c["lon"])], dtype=np.uint64)
    u, nb = np.unique(cel_c, return_counts=True)
    ids = np.array([h3i.str_to_int(s) for s in cellules], dtype=np.uint64)
    index = pd.Index(ids)
    total = np.zeros(len(ids))
    for d in range(0, len(u), 100_000):
        voisins = [np.asarray(h3i.grid_disk(int(x), k), dtype=np.uint64) for x in u[d:d + 100_000].tolist()]
        poids = np.repeat(nb[d:d + 100_000], [len(v) for v in voisins])
        j = index.get_indexer(np.concatenate(voisins))
        ok = j >= 0
        total += np.bincount(j[ok], poids[ok], minlength=len(ids))
    aires = np.array([h3i.cell_area(int(x), "km^2") for x in ids]) * (RAYON[corps] / 6_371_007.18) ** 2
    fenetre = aires * (3 * k * k + 3 * k + 1)
    print(f"  cratères >= {DIAMETRE_MIN_KM:g} km : {len(c):,}, fenêtre de {k} anneau(x) (~{fenetre.mean():.0f} km²)")
    return total / fenetre * 1000


# ------------------------------------------------------------------ écriture
def sources(corps: str, mnt: str, crat) -> dict:
    s = {"mnt": mnt}
    s["crateres"] = {"earth": "Earth Impact Database (PASSC)", "mars": "Robbins et Hynek 2012",
                     "moon": "Robbins 2018"}[corps] if crat is not None else "aucun"
    return s


def chemin_sortie(corps: str, res: int, base: int) -> tuple[str, Path]:
    nom = f"{MODULE}_{corps}_h3_{res}_b{base}"
    return nom, SORTIE / f"{nom}.parquet"


def ecrire(corps: str, res: int, base: int, t: pd.DataFrame, src: dict) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq
    SORTIE.mkdir(parents=True, exist_ok=True)
    t = t[COLONNES]
    nom, chemin = chemin_sortie(corps, res, base)
    tab = pa.Table.from_pandas(t, preserve_index=False)
    meta = {"module": MODULE, "corps": corps, "base_m": str(base), "sources": json.dumps(src, ensure_ascii=False)}
    tab = tab.replace_schema_metadata({**(tab.schema.metadata or {}), **{k: v.encode() for k, v in meta.items()}})
    pq.write_table(tab, chemin, compression="zstd")
    reconstruire_duckdb(SORTIE, corps)                          # copie des Parquet, refaite entièrement
    print(f"{NOMS[corps]}, base {base} m : {len(t):,} cellules écrites dans {court(chemin, RACINE)}")
    ti = t.set_index("h3")
    lignes = []
    for s, (la, lo) in SITES[corps].items():
        c = h3.latlng_to_cell(la, lo, res)
        if c not in ti.index:
            continue
        r = ti.loc[c]
        lignes.append({"site": s, "pente p50": round(r.pente_p50, 1), "pente p90": round(r.pente_p90, 1),
                       "< 5°": round(r.part_pente_inf_5, 2), "rugosité m": round(r.rugosite_rms, 1),
                       "dénivelé m": round(r.denivele_p5_p95), "courbure": round(r.courbure_moy, 3),
                       "cratères/1000 km²": round(r.densite_crateres, 2), "couverture": round(r.couverture, 2)})
    with pd.option_context("display.width", 250, "display.max_columns", None):
        if lignes:
            print(pd.DataFrame(lignes).to_string(index=False))
        print("Médianes :", t[["pente_p50", "pente_p90", "part_pente_inf_5", "rugosite_rms", "denivele_p5_p95",
                               "densite_crateres", "couverture"]].median().round(3).to_dict())


def crateres_seulement(args) -> None:
    import pyarrow.parquet as pq
    for corps in args.corps:
        fichiers = sorted(SORTIE.glob(f"{MODULE}_{corps}_h3_{args.resolution}_b*.parquet"))
        if not fichiers:
            print(f"{NOMS[corps]} : aucun résultat à mettre à jour dans {court(SORTIE, RACINE)}")
            continue
        crat = crateres(corps, args)
        for f in fichiers:
            t = pd.read_parquet(f)
            base = int(t["base_m"].iloc[0]) if len(t) else int(f.stem.rsplit("_b", 1)[1])
            src = json.loads((pq.read_schema(f).metadata or {}).get(b"sources", b"{}"))
            t["densite_crateres"] = densite_crateres(t["h3"].to_numpy(), crat, corps, args.resolution)
            ecrire(corps, args.resolution, base, t, sources(corps, src.get("mnt", "?"), crat))


def main() -> int:
    args = options()
    t0 = time.time()
    if args.crateres_seulement:
        crateres_seulement(args)
    else:
        for corps in ("moon", "mars", "earth"):
            if corps in args.corps:
                terre(args) if corps == "earth" else mnt_global(corps, args)
    print(f"\nTerminé en {(time.time() - t0) / 60:.1f} min.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
