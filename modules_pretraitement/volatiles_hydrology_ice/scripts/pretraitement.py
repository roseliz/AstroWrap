""""Volatiles, hydrology, ice and permafrost" module: preprocessing for Earth, Mars, and the Moon.

    ./pipeline run volatiles_hydrology_ice                       # all three bodies
    ./pipeline run volatiles_hydrology_ice --corps moon          # all options: --help

One row per H3 cell (resolution 5 by default; for Earth, land cells only), written to
pretreatment_data/volatiles_hydrology_ice/. All three bodies share the same columns; a column that is
irrelevant to a body is empty (NaN, unknown) or zero when the phenomenon does not exist (no stable liquid
water on Mars or the Moon). Quantities measured differently across bodies (soil water: moisture on Earth,
neutron hydrogen elsewhere) also include a within-body rank.

Sources
  Earth  ESA CCI Permafrost v5 (permafrost fraction and active layer thickness, 1 km), RGI 7.0 glaciers
         and Natural Earth continental ice, JRC Global Surface Water (surface water, 30 m), ESA CCI Soil
         Moisture (soil moisture, 0.25°), Natural Earth (land areas).
  Mars   SWIM 2.0 (subsurface ice consistency, 0-1 m, 1-5 m, > 5 m), Odyssey GRS (water equivalent,
         5°), perennial water ice from the Mars Climate Database.
  Moon   Diviner (ice stability, poles > 80°), Lunar Prospector (hydrogen, 0.5°), LOLA permanent
         shadows (65° to 90°), exposed ice seen by M3 (south pole, Lemelin et al. 2021).
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import h3
import numpy as np
import pandas as pd

RACINE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RACINE / "scripts"))
from commun import court, reconstruire_duckdb, verifier_espace  # noqa: E402
MODULE = "volatiles_hydrology_ice"
SORTIE = RACINE / "pretreatment_data" / MODULE
CACHE = RACINE / "cache" / MODULE
ENTREES = RACINE / "inputs" / MODULE

RAYON_KM = {"earth": 6371.0088, "mars": 3396.19, "moon": 1737.4}
PAS_TERRE = 0.05                          # degrés : grille des terres émergées de Natural Earth

# --- Colonnes (les mêmes sur les trois corps)
COLONNES = ["part_glace_surface", "indice_glace_sol", "profondeur_glace_m", "eau_sol_pct", "eau_sol_rang",
            "humidite_sol", "part_eau_libre", "part_ombre_permanente", "couverture", "fiabilite"]
# Indicateurs dont le taux de présence donne `couverture` : seuls ceux que le corps peut avoir
INDICATEURS = {"earth": ["part_glace_surface", "indice_glace_sol", "eau_sol_pct", "part_eau_libre"],
               "mars": ["part_glace_surface", "indice_glace_sol", "eau_sol_pct", "part_eau_libre"],
               "moon": ["indice_glace_sol", "eau_sol_pct", "part_ombre_permanente"]}

# --- Terre
URL_RGI = "https://daacdata.apps.nsidc.org/pub/DATASETS/nsidc0770_rgi_v7/"    # NSIDC-0770, demande l'identifiant Earthdata
URL_NE = "https://naciscdn.org/naturalearth/10m/physical/{nom}.zip"
ANNEES_PERMAFROST = (2021, 2022, 2023)    # v5.0 : 2021 à 2023
URL_CCI = ("https://dap.ceda.ac.uk/neodc/esacci/permafrost/data/{dossier}/L4/area4/pp/v05.0/{zone}/{an}/"
           "ESACCI-PERMAFROST-L4-{var}-MODISLST_CRYOGRID-{domaine}_PP-{an}-fv05.0.nc")
URL_SM = ("https://dap.ceda.ac.uk/neodc/esacci/soil_moisture/data/daily_files/COMBINED/v09.2/{an}/"
          "ESACCI-SOILMOISTURE-L3S-SSMV-COMBINED-{an}{mm:02d}{jj:02d}000000-fv09.2.nc")
URL_JRC = "https://storage.googleapis.com/global-surface-water/downloads2021/occurrence/occurrence_{lon}_{lat}v1_4_2021.tif"
OCCURRENCE_EAU = 50                       # % du temps en eau à partir duquel un pixel JRC est de l'eau libre
DENSITE_SOL = 1.4                         # g/cm³ : de l'humidité volumique à la masse d'eau par masse de sol
PETITE_GLACE_KM2 = 1.0                    # sous cette surface, un glacier RGI est compté dans la cellule de son centre
LIBRE_BLOC_MIN = 0.9                      # part libre d'un bloc de 5 km d'ESA CCI pour y retirer la glace (voir libre_antarctique)
T_SANS_PERGELISOL = 276.15                # K (+3 °C) : air plus chaud en moyenne annuelle -> pas de pergélisol (0, pas vide)
THERMIQUE = RACINE / "pretreatment_data" / "thermal_light_extrems" / "thermal_earth_h3_{res}.parquet"
# --- Mars
URL_SWIM = "https://swim.psi.edu/output/SWIM2/Global/Composite/SWIM2_{nom}.tif"
BANDES_SWIM = {"c0_1": 0.5, "c1_5": 3.0, "c_5": 5.0}      # tranche de profondeur -> profondeur retenue (m)
SEUIL_SWIM = 0.25                         # consistance (-1 à +1) à partir de laquelle une tranche compte pour la profondeur
                                          # (0,5 laissait Arcadia à 3 m, la glace y est dans le premier mètre : Byrne et al. 2009)
URL_GRS = "https://pds-geosciences.wustl.edu/ody/ody-m-grs-5-elements-v1/odgm_xxxx/data/smoothed/h2o_sr_5x5.tab"
SEUIL_GLACE_MARS = 1.0                    # kg/m² de glace d'eau en surface, tous les mois : glace pérenne
# --- Lune
URL_PSR = "https://pgda.gsfc.nasa.gov/data/MoonIllumination/LPSR_65{h}_240M_201608.TIF"
URL_PRP = "https://pds-geosciences.wustl.edu/lro/lro-l-dlre-4-rdr-v1/lrodlr_1001/data/prp/dlre_prp_{pole}.tab"
URL_LP = "https://pds-geosciences.wustl.edu/missions/lunarp/reduced/hydrogenhd.txt"
URL_LEMELIN = ("https://zenodo.org/records/4646092/files/"
               "Lemelin_et_al_2021_PSJ_south_pole_volatiles_ROIs_supp.zip?download=1")
PIXEL_M3_KM2 = 0.28 ** 2                  # un pixel M3 de 280 m (Li et al. 2018)
LAT_M3_SUD = -75.0                        # au-delà (vers le pôle sud), M3 a été cherché : pas de détection = 0
H2O_PAR_H = 18.015 / 2.016                # masse d'eau pour une masse d'hydrogène
COUVERTURE_PRP_MIN = 0.5                  # part de la cellule couverte par le maillage Diviner pour la garder
SITES = {
    "earth": {"Vallées sèches (Antarctique)": (-77.5, 162.0), "Vostok": (-78.46, 106.84), "Groenland": (72.6, -38.5),
              "Yakoutsk": (62.0, 129.7), "Barrow": (71.3, -156.8), "Atacama": (-24.5, -69.25),
              "Ténéré (Sahara)": (18.0, 10.0), "Lac Victoria": (-1.0, 33.0), "Amazonie": (-3.0, -60.0)},
    "mars": {"Arcadia Planitia": (47.0, -176.0), "Utopia Planitia": (46.7, 117.5), "Jezero": (18.44, 77.45),
             "Gale": (-4.59, 137.44), "Pôle nord": (88.0, 0.0), "Pôle sud": (-88.0, 0.0), "Meridiani": (-1.95, -5.53)},
    "moon": {"Shackleton": (-89.67, 129.78), "Cabeus": (-84.9, -35.5), "Faustini": (-87.3, 77.0),
             "Apollo 11": (0.674, 23.473), "Mare Imbrium": (32.8, -15.6), "Pôle nord": (89.5, 0.0)},
}


# ------------------------------------------------------------------ outils
def options() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--corps", nargs="+", choices=("earth", "mars", "moon"), default=["earth", "mars", "moon"])
    p.add_argument("--resolution", type=int, default=5, help="résolution H3 (défaut : 5)")
    p.add_argument("--zone", type=float, nargs=4, metavar=("OUEST", "SUD", "EST", "NORD"),
                   help="limiter le calcul à une boîte lat/lon (essais ; les téléchargements non terrestres restent entiers)")
    g = p.add_argument_group("Terre")
    g.add_argument("--annee-humidite", type=int, default=2022, help="année de l'humidité du sol (défaut : 2022)")
    g.add_argument("--pas-jours", type=int, default=7, help="un jour d'humidité sur N (défaut : 7, soit ~52 fichiers de 2,5 Mo)")
    g.add_argument("--annees-permafrost", type=int, nargs="+", default=list(ANNEES_PERMAFROST),
                   help="années du pergélisol, parmi 2021 à 2023 (défaut : les trois)")
    g.add_argument("--sans-jrc", action="store_true", help="ne pas lire JRC Global Surface Water (~16 Go à télécharger) : part_eau_libre vide")
    g.add_argument("--sans-rgi", action="store_true", help="ne pas télécharger RGI 7.0 (compte Earthdata) : glaciers de Natural Earth seulement")
    g.add_argument("--glace-seulement", action="store_true",
                   help="recalculer seulement part_glace_surface dans les résultats déjà écrits (RGI 7.0), sans rien retélécharger d'autre")
    g.add_argument("--rgi", type=Path, default=ENTREES / "rgi",
                   help=f"dossier des fichiers RGI 7.0 (zip ou shapefiles), sinon téléchargés (défaut : inputs/{MODULE}/rgi)")
    g = p.add_argument_group("Mars")
    g.add_argument("--mcd", type=Path, default=RACINE / "inputs" / "mcd", help="dossier de la MCD (défaut : inputs/mcd)")
    return p.parse_args()


def telecharger(url: str, cible: Path, tentatives: int = 8, silencieux: bool = False) -> bool:
    """Télécharge url dans cible (fichier .part renommé à la fin), en reprenant là où une coupure s'est arrêtée :
    certains serveurs (SWIM, PDS) ferment la connexion en cours de transfert."""
    if cible.is_file() and cible.stat().st_size > 0:
        return True
    cible.parent.mkdir(parents=True, exist_ok=True)
    partiel = cible.with_name(cible.name + ".part")
    for essai in range(tentatives):
        debut = partiel.stat().st_size if partiel.exists() else 0
        entetes = {"User-Agent": "Mozilla/5.0 (compatible; analogues-pipeline)"}   # SWIM refuse celui de Python
        if debut:
            entetes["Range"] = f"bytes={debut}-"
        requete = urllib.request.Request(url, headers=entetes)
        try:
            with urllib.request.urlopen(requete, timeout=60) as r:
                reprise = debut > 0 and r.status == 206
                if reprise:
                    total = int(r.headers.get("Content-Range", "bytes 0-0/0").rsplit("/", 1)[-1] or 0)
                else:
                    total = int(r.headers.get("Content-Length", 0))
                with open(partiel, "ab" if reprise else "wb") as f:
                    shutil.copyfileobj(r, f, 1 << 20)
            if total and partiel.stat().st_size != total:
                continue
            partiel.replace(cible)
            if not silencieux:
                print(f"  {cible.name} téléchargé ({cible.stat().st_size / 1e6:.1f} Mo)", flush=True)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 416 and partiel.exists():                      # déjà complet
                partiel.replace(cible)
                return True
            if e.code in (401, 403, 404):
                partiel.unlink(missing_ok=True)
                if not silencieux:
                    print(f"  {cible.name} : {e.code} ({url})")
                return False
            time.sleep(2 * (essai + 1))
        except (OSError, http.client.HTTPException):
            time.sleep(2 * (essai + 1))
    print(f"  {cible.name} : téléchargement impossible après {tentatives} essais ({url})")
    return False


def vers_cellules(lat, lon, res: int) -> np.ndarray:
    return np.array([h3.latlng_to_cell(a, b, res) for a, b in zip(np.asarray(lat, float).tolist(), np.asarray(lon, float).tolist())])


def cellules_globales(res: int, zone=None):
    cellules = np.array([c for r0 in h3.get_res0_cells() for c in h3.cell_to_children(r0, res)])
    centres = np.array([h3.cell_to_latlng(c) for c in cellules])
    lat_c, lon_c = centres[:, 0], centres[:, 1]
    if zone:
        garde = dans_zone(lat_c, lon_c, zone)
        cellules, lat_c, lon_c = cellules[garde], lat_c[garde], lon_c[garde]
    return cellules, lat_c, lon_c


def dans_zone(lat, lon, zone) -> np.ndarray:
    o, s, e, n = zone
    return (np.asarray(lon) >= o) & (np.asarray(lon) <= e) & (np.asarray(lat) >= s) & (np.asarray(lat) <= n)


def aire_cellules(cellules, corps: str) -> np.ndarray:
    """km² : h3 donne l'aire sur la sphère terrestre, à ramener au rayon du corps."""
    return np.array([h3.cell_area(c, unit="km^2") for c in cellules]) * (RAYON_KM[corps] / 6371.0088) ** 2


def rang(x) -> np.ndarray:
    """Rang parmi les cellules du corps, de 0 (la plus faible) à 1 (la plus forte) : part des autres cellules
    strictement plus faibles (les ex aequo ont le même rang) ; NaN reste NaN."""
    s = pd.Series(np.asarray(x, dtype=float))
    n = s.notna().sum()
    return ((s.rank(method="min") - 1) / max(n - 1, 1)).to_numpy(dtype=np.float32)


def indice_grille(valeurs, axe, periodique: bool) -> np.ndarray:
    """Case la plus proche d'une grille régulière (croissante ou décroissante)."""
    axe = np.asarray(axe, dtype=float)
    pas = np.diff(axe)
    if not np.allclose(pas, pas[0], rtol=1e-3, atol=1e-6):
        raise ValueError("grille irrégulière : interpolation non prévue")
    i = np.rint((np.asarray(valeurs, dtype=float) - axe[0]) / pas[0]).astype(np.int64)
    if periodique:
        i = np.mod(i, int(round(360 / abs(pas[0]))))
    return np.clip(i, 0, len(axe) - 1)


def sur_cellules(champ, lat_g, lon_g, lat_c, lon_c) -> np.ndarray:
    """Valeur du point de grille le plus proche du centre de chaque cellule (champ : lat × lon)."""
    return np.asarray(champ)[indice_grille(lat_c, lat_g, False), indice_grille(lon_c, lon_g, True)]


def somme_blocs(a: np.ndarray, bloc: int):
    """Somme et nombre de valeurs finies par bloc de bloc × bloc pixels."""
    nl, nc = a.shape[0] // bloc, a.shape[1] // bloc
    r = a[: nl * bloc, : nc * bloc].reshape(nl, bloc, nc, bloc)
    with np.errstate(invalid="ignore"):
        return np.nansum(r, axis=(1, 3)), np.isfinite(r).sum(axis=(1, 3)).astype(np.float64)


def accumuler(index: pd.Index, lat_b, lon_b, champs: dict, res: int, zone=None, tous: bool = False,
              lat_c=None, lon_c=None) -> dict:
    """Additionne dans les cellules H3 des champs portés par une grille de blocs (lat_b × lon_b), chacun de
    ses blocs allant dans la cellule qui contient son centre. champs : nom -> tableau 2D additif (sommes et
    comptes). tous=True : tous les blocs servent à repérer les cellules vides, qui prennent alors le bloc qui
    contient leur centre (grille de blocs plus grande qu'une cellule)."""
    n = len(index)
    forme = next(iter(champs.values())).shape
    utile = np.ones(forme, bool) if tous else np.logical_or.reduce([v != 0 for v in champs.values()])
    il, jl = np.nonzero(utile)
    la, lo = np.asarray(lat_b)[il], np.asarray(lon_b)[jl]
    if zone:
        g = dans_zone(la, lo, zone)
        il, jl, la, lo = il[g], jl[g], la[g], lo[g]
    pos = index.get_indexer(vers_cellules(la, lo, res))
    ok = pos >= 0
    sortie = {k: np.bincount(pos[ok], weights=v[il, jl][ok].astype(float), minlength=n) for k, v in champs.items()}
    if tous and lat_c is not None:
        vides = np.bincount(pos[ok], minlength=n) == 0
        if vides.any():
            pl, po = lat_b[1] - lat_b[0], lon_b[1] - lon_b[0]
            fi = (lat_c[vides] - lat_b[0]) / pl
            fj = (lon_c[vides] - lon_b[0]) / po
            i = np.clip(np.rint(fi).astype(int), 0, len(lat_b) - 1)
            j = np.clip(np.rint(fj).astype(int), 0, len(lon_b) - 1)
            dans = (fi > -0.5) & (fi < len(lat_b) - 0.5) & (fj > -0.5) & (fj < len(lon_b) - 0.5)
            for k, v in champs.items():
                sortie[k][vides] = np.where(dans, v[i, j], 0)
    return sortie


def moyenne(somme, nombre) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(nombre > 0, somme / np.maximum(nombre, 1e-12), np.nan).astype(np.float32)


def assembler(corps: str, res: int, cellules, v: dict) -> pd.DataFrame:
    n = len(cellules)
    nan = np.full(n, np.nan, dtype=np.float32)
    t = pd.DataFrame({"body": corps, "resolution": res, "h3": cellules})
    for c in ("part_glace_surface", "indice_glace_sol", "profondeur_glace_m", "eau_sol_pct", "humidite_sol",
              "part_eau_libre", "part_ombre_permanente"):
        t[c] = np.asarray(v.get(c, nan), dtype=np.float32)
    t["eau_sol_rang"] = rang(t["eau_sol_pct"])
    t["couverture"] = t[INDICATEURS[corps]].notna().mean(axis=1).astype(np.float32)
    t["fiabilite"] = t["couverture"]                                       # provisoire, même règle que les autres modules
    return t[["body", "resolution", "h3", *COLONNES]]


def ecrire(corps: str, res: int, t: pd.DataFrame, sources: dict) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq
    SORTIE.mkdir(parents=True, exist_ok=True)
    chemin = SORTIE / f"{MODULE}_{corps}_h3_{res}.parquet"
    tab = pa.Table.from_pandas(t, preserve_index=False)
    meta = {"module": MODULE, "corps": corps, "sources": json.dumps(sources, ensure_ascii=False),
            "indicateurs": json.dumps(INDICATEURS[corps])}
    tab = tab.replace_schema_metadata({**(tab.schema.metadata or {}), **{k: v.encode() for k, v in meta.items()}})
    pq.write_table(tab, chemin, compression="zstd")
    reconstruire_duckdb(SORTIE, corps)                          # copie des Parquet, refaite entièrement
    print(f"{corps} : {len(t):,} cellules écrites dans {court(chemin, RACINE)}")
    ti = t.set_index("h3")
    cols = [c for c in COLONNES if c not in ("eau_sol_rang", "fiabilite")]
    lignes = []
    for s, (la, lo) in SITES[corps].items():
        c = h3.latlng_to_cell(la, lo, res)
        lignes.append({"site": s, **(ti.loc[c, cols].to_dict() if c in ti.index else {"remarque": "hors des cellules"})})
    with pd.option_context("display.width", 250, "display.max_columns", None):
        print(pd.DataFrame(lignes).round(3).to_string(index=False))
        print(t[cols].describe().round(3).to_string())


def ne_forme(nom: str) -> Path:
    """Fichier .shp d'une couche Natural Earth (domaine public), téléchargée une fois dans cache/."""
    dossier = CACHE / "natural_earth" / nom
    trouves = sorted(dossier.glob("*.shp")) if dossier.is_dir() else []
    if not trouves:
        archive = CACHE / "natural_earth" / f"{nom}.zip"
        if not telecharger(URL_NE.format(nom=nom), archive):
            raise SystemExit(f"Natural Earth ({nom}) introuvable : Terre impossible sans les terres émergées")
        with zipfile.ZipFile(archive) as z:
            z.extractall(dossier)
        archive.unlink(missing_ok=True)
        trouves = sorted(dossier.glob("*.shp"))
    return trouves[0]


# ------------------------------------------------------------------ Terre
def terres_emergees(args) -> dict:
    """Cellules de terre émergée : celles qui contiennent le centre d'au moins un pixel de 0,05° de Natural Earth.
    Garde aussi, pour chaque pixel de terre, la cellule où il tombe (agrégation des glaces et de l'humidité)."""
    import geopandas as gpd
    from rasterio import features
    from rasterio.transform import from_origin
    gdf = gpd.read_file(ne_forme("ne_10m_land"))
    tr = from_origin(-180, 90, PAS_TERRE, PAS_TERRE)
    forme = (int(round(180 / PAS_TERRE)), int(round(360 / PAS_TERRE)))
    masque = features.rasterize(((g, 1) for g in gdf.geometry if g is not None), out_shape=forme, transform=tr,
                                fill=0, dtype="uint8").astype(bool)
    lig, col = np.nonzero(masque)
    lat, lon = 90 - PAS_TERRE * (lig + 0.5), -180 + PAS_TERRE * (col + 0.5)
    if args.zone:
        g = dans_zone(lat, lon, args.zone)
        lig, col, lat, lon = lig[g], col[g], lat[g], lon[g]
        masque = np.zeros_like(masque)
        masque[lig, col] = True
    t0 = time.time()
    cell_pix = vers_cellules(lat, lon, args.resolution)
    cellules, inverse = np.unique(cell_pix, return_inverse=True)
    centres = np.array([h3.cell_to_latlng(c) for c in cellules])
    print(f"  {len(cellules):,} cellules de terre émergée ({time.time() - t0:.0f} s)")
    return {"cellules": cellules, "lat_c": centres[:, 0], "lon_c": centres[:, 1], "lig": lig, "col": col,
            "inverse": inverse, "n_pix": np.bincount(inverse, minlength=len(cellules)).astype(float),
            "masque": masque, "tr": tr, "forme": forme}


def temperature_air(cellules, res: int) -> np.ndarray | None:
    """Température moyenne annuelle de l'air (K) par cellule, lue dans le résultat du module thermal_light_extrems
    (MERRA-2) s'il existe ; None sinon. Sert seulement à mettre 0 là où le pergélisol est impossible."""
    f = Path(str(THERMIQUE).format(res=res))
    if not f.is_file():
        print(f"  {court(f, RACINE)} absent : pas de 0 de pergélisol au sud de 25° N (lancer thermal_light_extrems d'abord)")
        return None
    t = pd.read_parquet(f, columns=["h3", "air_temperature_mean"]).drop_duplicates("h3").set_index("h3")
    return t["air_temperature_mean"].reindex(np.asarray(cellules)).to_numpy(dtype=float)


def zero_hors_pergelisol(indice, lat_c, part_glace, t_air=None) -> np.ndarray:
    """ESA CCI Permafrost ne donne une valeur qu'à l'intérieur de la zone où le pergélisol est possible (au nord de
    25° N : 0 % y est une vraie valeur, mais Montréal ou Moscou sont vides). Une cellule vide qui n'est pas sous une
    glace continentale n'a pas de pergélisol, donc 0 : au nord de 25° N (domaine de CCI), et partout où l'air est en
    moyenne annuelle au-dessus de +3 °C (t_air, module thermique) : Sahara, Australie, Amazonie. Restent vides
    les cellules froides hors du domaine (Andes, Antarctique sous la glace) : inconnu."""
    indice = np.asarray(indice, dtype=np.float32).copy()
    lat_c = np.asarray(lat_c, dtype=float)
    libre = ~np.isfinite(indice) & (np.asarray(part_glace, dtype=float) < 0.5)
    zero = libre & (lat_c >= 25) & (lat_c <= 85)
    if t_air is not None:
        with np.errstate(invalid="ignore"):
            zero |= libre & (np.asarray(t_air, dtype=float) > T_SANS_PERGELISOL)
    indice[zero] = 0.0
    return indice


def maj_glace(args) -> None:
    """Recalcule part_glace_surface (et indice_glace_sol hors pergélisol, couverture) dans le résultat de la Terre déjà écrit : le plus long de la
    Terre (JRC, humidité, pergélisol) n'est pas refait."""
    import pyarrow.parquet as pq
    chemin = SORTIE / f"{MODULE}_earth_h3_{args.resolution}.parquet"
    if not chemin.is_file():
        print(f"  {court(chemin, RACINE)} absent : lancer d'abord le calcul complet de la Terre")
        return
    print("\n=== Terre : glace de surface seulement")
    meta = pq.read_schema(chemin).metadata or {}
    sources = json.loads(meta.get(b"sources", b"{}").decode())
    t = pd.read_parquet(chemin)
    T = terres_emergees(args)
    pos = pd.Index(t["h3"]).get_indexer(T["cellules"])
    part, sources["glace_surface"] = glace_surface(args, T)
    nouveau = np.full(len(t), np.nan, np.float32)
    ok = pos >= 0
    nouveau[pos[ok]] = part[ok]
    t["part_glace_surface"] = nouveau
    lat_t = np.full(len(t), np.nan)
    lat_t[pos[ok]] = T["lat_c"][ok]
    t["indice_glace_sol"] = zero_hors_pergelisol(t["indice_glace_sol"], lat_t, t["part_glace_surface"].fillna(0),
                                                 temperature_air(t["h3"], args.resolution))
    t["couverture"] = t[INDICATEURS["earth"]].notna().mean(axis=1).astype(np.float32)
    t["fiabilite"] = t["couverture"]
    ecrire("earth", args.resolution, t, sources)


def terre(args) -> None:
    print("\n=== Terre")
    res = args.resolution
    T = terres_emergees(args)
    cellules, lat_c, lon_c = T["cellules"], T["lat_c"], T["lon_c"]
    index = pd.Index(cellules)
    v, sources = {}, {}

    v["part_glace_surface"], sources["glace_surface"] = glace_surface(args, T)
    sources["pergelisol"] = "ESA CCI Permafrost v5.0 (PFR et ALT, 1 km, MODIS LST + CryoGrid), années " + ", ".join(map(str, args.annees_permafrost))
    v["indice_glace_sol"], v["profondeur_glace_m"] = permafrost(args, index, res)
    v["indice_glace_sol"] = zero_hors_pergelisol(v["indice_glace_sol"], lat_c, v["part_glace_surface"],
                                                 temperature_air(cellules, res))
    v["humidite_sol"] = humidite_sol(args, lat_c, lon_c)
    sources["humidite_sol"] = f"ESA CCI Soil Moisture COMBINED v09.2, {args.annee_humidite}, un jour sur {args.pas_jours}"
    v["eau_sol_pct"] = (100 * v["humidite_sol"] / DENSITE_SOL).astype(np.float32)   # estimation : eau / masse de sol
    sources["eau_sol_pct"] = f"humidité volumique du sol / densité apparente {DENSITE_SOL} g/cm³ (estimation)"
    if args.sans_jrc:
        v["part_eau_libre"] = np.full(len(cellules), np.nan, np.float32)
    else:
        v["part_eau_libre"] = eau_libre(args, T, index)
        sources["eau_libre"] = f"JRC Global Surface Water v1.4 (2021), occurrence >= {OCCURRENCE_EAU} %"
    v["part_ombre_permanente"] = np.zeros(len(cellules), np.float32)
    ecrire("earth", res, assembler("earth", res, cellules, v), sources)


def libre_antarctique(args):
    """Part de sol libre de glace de l'Antarctique, par blocs de 5 × 5 pixels de 0,01° : ESA CCI Permafrost
    (domaine AREA27) n'a de valeurs que sur le sol libre de glace (affleurements, Vallées sèches). Son masque
    couvre ~183 500 km², 4 à 8 fois les inventaires (21 745 km², Burton-Johnson et al. 2016 ; ~45 000 km² dans
    la base SCAR plus ancienne) : un pixel de 1 km qui touche un affleurement compte en entier. Seuls les blocs
    libres à LIBRE_BLOC_MIN (90 %) au moins sont gardés : ~48 000 km², les Vallées sèches entières, pas les
    nunataks isolés. Moyenne des années lues ; (part, lat_b, lon_b), ou None si aucun fichier n'est lisible."""
    parts, lat_b = [], None
    for an in args.annees_permafrost:
        url = URL_CCI.format(dossier="permafrost_extent", zone="Antarctica", an=an, var="PFR", domaine="AREA27")
        f = CACHE / "permafrost" / Path(url).name
        if not telecharger(url, f):
            continue
        _, nombre, lat_b, lon_b = blocs_netcdf(f, "PFR", 5)
        parts.append(nombre / 25)
    if not parts:
        return None
    part = np.mean(parts, axis=0)
    return np.where(part >= LIBRE_BLOC_MIN, part, 0.0), lat_b, lon_b


def glace_surface(args, T):
    """Part de chaque cellule couverte de glace : max de RGI 7.0 (glaciers, calottes) et de Natural Earth
    (inlandsis du Groenland et de l'Antarctique, absents de RGI). Natural Earth couvre tout l'Antarctique, Vallées
    sèches comprises : on y retire, pixel par pixel, le sol libre de glace d'ESA CCI Permafrost."""
    import geopandas as gpd
    from rasterio import features
    cellules, n_pix = T["cellules"], T["n_pix"]
    gdf = gpd.read_file(ne_forme("ne_10m_glaciated_areas"))
    glace = features.rasterize(((g, 1) for g in gdf.geometry if g is not None), out_shape=T["forme"], transform=T["tr"],
                               fill=0, dtype="uint8")
    g_pix = glace[T["lig"], T["col"]].astype(float)
    lat_pix = 90 - PAS_TERRE * (T["lig"] + 0.5)
    sud = (lat_pix < -60) & (g_pix > 0)
    libre = libre_antarctique(args) if sud.any() else None
    if libre is not None:
        part_libre, lat_b, lon_b = libre
        lon_pix = -180 + PAS_TERRE * (T["col"][sud] + 0.5)
        dans = (lat_pix[sud] >= min(lat_b[0], lat_b[-1])) & (lat_pix[sud] <= max(lat_b[0], lat_b[-1]))
        if abs(lon_b[-1] - lon_b[0]) < 359:                              # grille partielle en longitude
            dans &= (lon_pix >= min(lon_b[0], lon_b[-1])) & (lon_pix <= max(lon_b[0], lon_b[-1]))
        f = np.where(dans, sur_cellules(part_libre, lat_b, lon_b, lat_pix[sud], lon_pix), 0.0)
        g_pix[sud] = 1 - np.clip(np.nan_to_num(f), 0, 1)
        print(f"  Antarctique : {int((f > 0).sum()):,} pixels de 0,05° en partie libres de glace (ESA CCI Permafrost)")
    elif sud.any():
        print("  sol libre de glace de l'Antarctique introuvable : Natural Earth couvre tout le continent, Vallées sèches comprises")
    part_ne = np.bincount(T["inverse"], weights=g_pix, minlength=len(cellules)) / n_pix
    print(f"  glace de Natural Earth : {int((part_ne > 0).sum()):,} cellules")
    part, source = part_ne, "Natural Earth (glaciers et inlandsis" + (", moins le sol libre de l'Antarctique d'ESA CCI)" if libre is not None else ")")
    if not args.sans_rgi:
        fichiers = fichiers_rgi(args)
        if fichiers:
            part_rgi = part_rgi_cellules(fichiers, cellules, args.resolution, args.zone)
            part = np.maximum(part_ne, part_rgi)
            source = "RGI 7.0 (glaciers) et " + source + ", le plus grand des deux par cellule"
        else:
            print("  RGI 7.0 indisponible : glace de Natural Earth seulement (source_glace dans les métadonnées)")
    return np.clip(part, 0, 1).astype(np.float32), source


def charger_env() -> None:
    """Lit RACINE/.env (ignoré par git) : lignes CLE=valeur. EARTHDATA_USERNAME et EARTHDATA_PASSWORD, ou
    USERNAME_EARTHACCESS et PASSWORD_EARTHACCESS. Ne remplace pas ce qui est déjà dans l'environnement."""
    f = RACINE / ".env"
    if not f.is_file():
        return
    valeurs = {}
    for ligne in f.read_text(encoding="utf-8", errors="ignore").splitlines():
        ligne = ligne.strip()
        if ligne and not ligne.startswith("#") and "=" in ligne:
            cle, _, v = ligne.partition("=")
            valeurs[cle.strip().removeprefix("export ").strip()] = v.strip().strip("\"'")
    for cible, noms in (("EARTHDATA_USERNAME", ("EARTHDATA_USERNAME", "USERNAME_EARTHACCESS")),
                        ("EARTHDATA_PASSWORD", ("EARTHDATA_PASSWORD", "PASSWORD_EARTHACCESS"))):
        for nom in noms:
            if nom in valeurs and valeurs[nom] and cible not in os.environ:
                os.environ[cible] = valeurs[nom]


def charger_netrc() -> None:
    """Sous Windows, earthaccess ne cherche que ~/_netrc alors que setup.sh et la doc NASA écrivent ~/.netrc :
    on lit l'un ou l'autre avec la bibliothèque standard et on passe par les variables d'environnement."""
    import netrc
    if os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD"):
        return
    for nom in (".netrc", "_netrc"):
        try:
            a = netrc.netrc(str(Path.home() / nom)).authenticators("urs.earthdata.nasa.gov")
        except (OSError, netrc.NetrcParseError):
            continue
        if a and a[0] and a[2]:
            os.environ["EARTHDATA_USERNAME"], os.environ["EARTHDATA_PASSWORD"] = a[0], a[2]
            return


def connexion_earthdata():
    """earthaccess connecté, ou None. Ordre : variables d'environnement (y compris .env), puis ~/.netrc, puis, si
    le programme tourne dans un terminal, la demande de l'identifiant et du mot de passe au clavier. Sans terminal
    (tmux détaché, tâche en arrière-plan) on n'attend jamais : RGI est facultatif."""
    import earthaccess
    charger_env()
    charger_netrc()
    strategies = ["environment", "netrc"] + (["interactive"] if sys.stdin is not None and sys.stdin.isatty() else [])
    for strategie in strategies:
        if strategie == "interactive":
            print("  Identifiant NASA Earthdata absent de .env et de ~/.netrc : saisie au clavier "
                  "(compte gratuit sur https://urs.earthdata.nasa.gov ; Ctrl+C pour continuer sans RGI)")
        try:
            if earthaccess.login(strategy=strategie).authenticated:
                return earthaccess
        except KeyboardInterrupt:
            print("\n  connexion abandonnée")
            return None
        except Exception:
            continue
    print("  pas d'identifiant Earthdata (.env, ~/.netrc, ou un terminal pour le saisir) : RGI 7.0 ignoré")
    return None


def zips_rgi(session, base: str, profondeur: int = 3) -> list[str]:
    """Explore le dossier de NSIDC (pages d'index Apache) et rend les zips des contours de glaciers (« -G- »), de
    préférence par région ; le fichier mondial seulement s'il n'y a pas de fichiers régionaux."""
    vus, zips, a_voir = set(), [], [(base, 0)]
    while a_voir:
        url, niveau = a_voir.pop(0)
        if url in vus:
            continue
        vus.add(url)
        try:
            r = session.get(url, timeout=60)
            r.raise_for_status()
        except Exception:
            continue
        for href in re.findall(r'href="([^"?#]+)"', r.text, re.I):
            if href.startswith(("/", "..", "http", "mailto")):
                continue
            if href.lower().endswith(".zip") and "-G-" in href:
                zips.append(url + href)
            elif href.endswith("/") and niveau < profondeur:
                a_voir.append((url + href, niveau + 1))
    regionaux = [z for z in zips if "global" not in z.lower()]
    return sorted(set(regionaux or zips))


def fichiers_rgi(args) -> list[Path]:
    """Contours RGI 7.0 : fichiers déjà dans --rgi, sinon téléchargés depuis NSIDC (compte Earthdata)."""
    def locaux():
        if not args.rgi.is_dir():
            return []
        zips = [f for f in sorted(args.rgi.rglob("*.zip")) if "-G-" in f.name or "RGI" in f.name.upper()]
        for z in zips:                                                    # extraire une fois
            dest = z.with_suffix("")
            if not dest.is_dir():
                with zipfile.ZipFile(z) as arc:
                    arc.extractall(dest)
        formes = [f for f in sorted(args.rgi.rglob("*.shp")) if "-G-" in f.name and "global" not in f.name]
        formes = formes or [f for f in sorted(args.rgi.rglob("*.shp")) if "-G-" in f.name]
        return formes or sorted(args.rgi.rglob("*.shp"))
    trouves = locaux()
    if trouves:
        return trouves
    try:
        earthaccess = connexion_earthdata()
        if earthaccess is None:
            return []
        # La collection NSIDC-0770 n'a pas de granules dans CMR (search_data renvoie 0) : on explore le dossier du serveur
        # de données de NSIDC avec la session authentifiée, puis on télécharge les zips des contours de glaciers.
        session = earthaccess.get_requests_https_session()
        liens = zips_rgi(session, URL_RGI)
        if not liens:
            print(f"  RGI 7.0 : aucun zip trouvé sous {URL_RGI} (autoriser l'application NSIDC dans le profil Earthdata ? "
                  f"sinon télécharger les RGI2000-v7.0-G-*.zip à la main dans {court(args.rgi, RACINE)})")
            return []
        print(f"  RGI 7.0 : {len(liens)} fichiers chez NSIDC")
        args.rgi.mkdir(parents=True, exist_ok=True)
        for lien in liens:
            cible = args.rgi / lien.rsplit("/", 1)[-1]
            if cible.is_file() and cible.stat().st_size > 0:
                continue
            partiel = cible.with_name(cible.name + ".part")
            with session.get(lien, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(partiel, "wb") as f:
                    shutil.copyfileobj(r.raw, f, 1 << 20)
            partiel.replace(cible)
            print(f"  {cible.name} téléchargé ({cible.stat().st_size / 1e6:.0f} Mo)", flush=True)
    except Exception as e:                                                # hors ligne, compte refusé : on continue sans RGI
        print(f"  RGI 7.0 non téléchargé ({e})")
        return []
    return locaux()


def part_rgi_cellules(fichiers: list[Path], cellules, res: int, zone) -> np.ndarray:
    """Part de chaque cellule couverte de glaciers : surface des contours / surface de la cellule. Un glacier
    de moins de PETITE_GLACE_KM2 est compté dans la cellule de son centre ; les autres par sous-cellules H3
    (res + 3, 343 par cellule) dont le centre tombe dans le contour."""
    import geopandas as gpd
    index = pd.Index(cellules)
    km2 = np.zeros(len(cellules))
    aire_fine = h3.average_hexagon_area(res + 3, unit="km^2")
    for f in fichiers:
        gdf = gpd.read_file(f)
        gdf = gdf[gdf.geometry.notna() & gdf.geom_type.isin(["Polygon", "MultiPolygon"])]
        if gdf.empty:
            continue
        if gdf.crs is not None and gdf.crs.is_projected:
            gdf = gdf.to_crs(gdf.crs.geodetic_crs)
        if "area_km2" not in gdf:
            gdf["area_km2"] = gdf.to_crs(epsg=6933).area / 1e6
        pts = gdf.geometry.representative_point()
        if zone:
            g = np.asarray(dans_zone(pts.y.to_numpy(), pts.x.to_numpy(), zone))
            gdf, pts = gdf[g], pts[g]
        petits = gdf["area_km2"].to_numpy() < PETITE_GLACE_KM2
        pos = index.get_indexer(vers_cellules(pts.y.to_numpy()[petits], pts.x.to_numpy()[petits], res))
        ok = pos >= 0
        np.add.at(km2, pos[ok], gdf["area_km2"].to_numpy()[petits][ok])
        fines = []
        for geom in gdf.geometry[~petits]:
            fines.extend(h3.cell_to_parent(c, res) for c in h3.geo_to_cells(geom, res + 3))
        if fines:
            comptes = pd.Series(fines).value_counts()
            pos = index.get_indexer(comptes.index)
            ok = pos >= 0
            np.add.at(km2, pos[ok], comptes.to_numpy()[ok] * aire_fine)
        print(f"  RGI : {f.name}, {len(gdf):,} glaciers, {gdf['area_km2'].sum():,.0f} km²")
    aire = np.array([h3.cell_area(c, unit="km^2") for c in cellules])
    return np.clip(km2 / aire, 0, 1)


def blocs_netcdf(chemin: Path, var: str, bloc: int):
    """Somme et nombre de valeurs valides par bloc de bloc × bloc pixels, lus par bandes de lignes."""
    import xarray as xr
    with xr.open_dataset(chemin) as ds:
        da = ds[var].isel(time=0) if "time" in ds[var].dims else ds[var]
        lat, lon = ds["lat"].values.astype(float), ds["lon"].values.astype(float)
        nl, nc = len(lat) // bloc, len(lon) // bloc
        somme, nombre = np.zeros((nl, nc)), np.zeros((nl, nc))
        pas = 50 * bloc
        for d in range(0, nl * bloc, pas):
            f = min(d + pas, nl * bloc)
            s, n = somme_blocs(da.isel(lat=slice(d, f)).values.astype(np.float32), bloc)
            somme[d // bloc: f // bloc], nombre[d // bloc: f // bloc] = s, n
    lat_b = lat[: nl * bloc].reshape(nl, bloc).mean(axis=1)
    lon_b = lon[: nc * bloc].reshape(nc, bloc).mean(axis=1)
    return somme, nombre, lat_b, lon_b


def permafrost(args, index: pd.Index, res: int):
    """ESA CCI Permafrost v5.0, hémisphère nord (25° à 85° N) et Antarctique (60° à 85° S), sol libre de glace :
    fraction de pergélisol (0-1) et épaisseur de la couche active (m), moyennes sur les années choisies. Ailleurs
    (tropiques, glaciers, mers) : NaN."""
    n = len(index)
    cumul = {k: np.zeros(n) for k in ("pfr_s", "pfr_n", "alt_s", "alt_n")}
    for zone_nom, domaine in (("northern_hemisphere", "AREA4"), ("Antarctica", "AREA27")):
        blocs = {}
        for an in args.annees_permafrost:
            for var, dossier, cle in (("PFR", "permafrost_extent", "pfr"), ("ALT", "active_layer_thickness", "alt")):
                url = URL_CCI.format(dossier=dossier, zone=zone_nom, an=an, var=var, domaine=domaine)
                f = CACHE / "permafrost" / Path(url).name
                if not telecharger(url, f):
                    continue
                s, nb, lat_b, lon_b = blocs_netcdf(f, var, 5)             # blocs de 0,05° (~5,5 km)
                blocs[f"{cle}_s"] = blocs.get(f"{cle}_s", 0) + s
                blocs[f"{cle}_n"] = blocs.get(f"{cle}_n", 0) + nb
        if not blocs:
            print(f"  pergélisol ({zone_nom}) introuvable : laissé vide")
            continue
        for k in ("pfr_s", "pfr_n", "alt_s", "alt_n"):
            blocs.setdefault(k, np.zeros_like(blocs["pfr_n"]))
        r = accumuler(index, lat_b, lon_b, blocs, res, args.zone)
        for k in cumul:
            cumul[k] += r[k]
        print(f"  pergélisol ({zone_nom}) : {int((r['pfr_n'] > 0).sum()):,} cellules")
    indice = moyenne(cumul["pfr_s"], cumul["pfr_n"]) / 100
    return indice, moyenne(cumul["alt_s"], cumul["alt_n"])


def humidite_sol(args, lat_c, lon_c) -> np.ndarray:
    """Humidité volumique du sol (m³/m³) : moyenne d'un jour sur --pas-jours de l'année, 0,25° ; au moins 5 jours."""
    import xarray as xr
    jour, fin = date(args.annee_humidite, 1, 1), date(args.annee_humidite, 12, 31)
    somme = nombre = lat_g = lon_g = None
    lus = 0
    while jour <= fin:
        url = URL_SM.format(an=jour.year, mm=jour.month, jj=jour.day)
        f = CACHE / "humidite_sol" / Path(url).name
        if telecharger(url, f, tentatives=3, silencieux=True):
            with xr.open_dataset(f) as ds:
                a = ds["sm"].isel(time=0).values.astype(np.float32)
                if lat_g is None:
                    lat_g, lon_g = ds["lat"].values.astype(float), ds["lon"].values.astype(float)
            f.unlink(missing_ok=True)
            ok = np.isfinite(a)
            somme = np.where(ok, a, 0.0) if somme is None else somme + np.where(ok, a, 0.0)
            nombre = ok.astype(np.int32) if nombre is None else nombre + ok
            lus += 1
        jour += timedelta(days=args.pas_jours)
    if somme is None:
        print("  humidité du sol introuvable : humidite_sol et eau_sol_pct laissées vides")
        return np.full(len(lat_c), np.nan, np.float32)
    moy = np.where(nombre >= 5, somme / np.maximum(nombre, 1), np.nan)
    print(f"  humidité du sol : {lus} jours lus")
    return sur_cellules(moy, lat_g, lon_g, lat_c, lon_c).astype(np.float32)


def eau_libre(args, T, index: pd.Index) -> np.ndarray:
    """JRC Global Surface Water : part des pixels de terre émergée en eau plus de OCCURRENCE_EAU % du temps. Les
    tuiles de 10° (~100 Mo en moyenne) sont téléchargées, lues par blocs de 0,025° puis effacées une à une."""
    import rasterio
    from rasterio.windows import Window
    lat_c, lon_c = T["lat_c"], T["lon_c"]
    tuiles = sorted({(int(10 * math.floor(lo / 10)), int(10 * math.ceil(la / 10))) for la, lo in zip(lat_c, lon_c) if -60 < la <= 80})
    nom = lambda lo, la: URL_JRC.format(lon=f"{abs(lo)}{'E' if lo >= 0 else 'W'}", lat=f"{abs(la)}{'N' if la >= 0 else 'S'}")
    print(f"  JRC : {len(tuiles)} tuiles à lire")
    verifier_espace(CACHE / "jrc", 3, "les tuiles JRC")
    n = len(index)
    eau, vu = np.zeros(n), np.zeros(n)
    BLOC, PAS_B = 100, 0.025                                              # pixels de 0,00025° -> blocs de 0,025°
    masque, ntr = T["masque"], T["tr"]

    def prendre(k):
        lo, la = tuiles[k]
        f = CACHE / "jrc" / Path(nom(lo, la)).name
        return f if telecharger(nom(lo, la), f, silencieux=True) else None

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=1) as pool:
        suivant = pool.submit(prendre, 0) if tuiles else None
        for k, (lo, la) in enumerate(tuiles):
            f = suivant.result()
            suivant = pool.submit(prendre, k + 1) if k + 1 < len(tuiles) else None
            if f is None:
                continue
            try:
                with rasterio.open(f) as src:
                    nl, nc = src.height // BLOC, src.width // BLOC
                    w_eau, w_obs = np.zeros((nl, nc)), np.zeros((nl, nc))
                    for d in range(0, nl * BLOC, 40 * BLOC):
                        h = min(40 * BLOC, nl * BLOC - d)
                        a = src.read(1, window=Window(0, d, nc * BLOC, h))
                        r = a.reshape(h // BLOC, BLOC, nc, BLOC)
                        w_eau[d // BLOC: (d + h) // BLOC] = ((r >= OCCURRENCE_EAU) & (r <= 100)).sum(axis=(1, 3))
                        w_obs[d // BLOC: (d + h) // BLOC] = (r != 255).sum(axis=(1, 3))
                pas_b = 10.0 / nl
                lat_b = la - pas_b * (np.arange(nl) + 0.5)
                lon_b = lo + pas_b * (np.arange(nc) + 0.5)
                # seulement les blocs sur la terre émergée (la mer est de l'eau pour JRC, pas pour ce module)
                li = np.clip(((90 - lat_b) / PAS_TERRE).astype(int), 0, masque.shape[0] - 1)
                ci = np.clip(((lon_b + 180) / PAS_TERRE).astype(int), 0, masque.shape[1] - 1)
                sur_terre = masque[np.ix_(li, ci)]
                r = accumuler(index, lat_b, lon_b, {"eau": np.where(sur_terre, w_eau, 0), "obs": np.where(sur_terre, w_obs, 0)},
                              args.resolution, args.zone)
                eau += r["eau"]
                vu += r["obs"]
            except Exception as e:                                        # une tuile illisible ne doit pas tout perdre
                print(f"  JRC {f.name} illisible ({e})")
            finally:
                f.unlink(missing_ok=True)
            if (k + 1) % 10 == 0 or k + 1 == len(tuiles):
                print(f"    {k + 1}/{len(tuiles)} tuiles ({(time.time() - t0) / 60:.0f} min)", flush=True)
    return moyenne(eau, vu)


# ------------------------------------------------------------------ Mars
def mars(args) -> None:
    print("\n=== Mars")
    res = args.resolution
    cellules, lat_c, lon_c = cellules_globales(res, args.zone)
    index = pd.Index(cellules)
    n = len(cellules)
    print(f"  {n:,} cellules H3 de résolution {res}")
    v, sources = {}, {}
    v["indice_glace_sol"], v["profondeur_glace_m"] = swim(index, cellules, lat_c, lon_c, res, args.zone)
    sources["glace_sol"] = "SWIM 2.0 (Putzig et al., consistance avec la glace souterraine, 0-1 m, 1-5 m, > 5 m)"
    v["eau_sol_pct"] = grs_h2o(lat_c, lon_c)
    sources["eau_sol"] = "Mars Odyssey GRS, H2O (% massique), grille de 5° lissée (Boynton et al.)"
    v["part_glace_surface"] = glace_perenne_mcd(args.mcd, lat_c, lon_c)
    sources["glace_surface"] = "Mars Climate Database v6.2 : glace d'eau en surface tous les mois"
    v["part_eau_libre"] = np.zeros(n, np.float32)                         # pas d'eau liquide stable en surface
    v["part_ombre_permanente"] = np.zeros(n, np.float32)                  # pas d'ombre permanente sur Mars
    ecrire("mars", res, assembler("mars", res, cellules, v), sources)


def swim(index, cellules, lat_c, lon_c, res, zone):
    """Consistance de la glace souterraine : indice = la plus forte consistance positive des trois tranches de
    profondeur (0 si aucune n'est consistante) ; profondeur = tranche la moins profonde dont la consistance
    atteint SEUIL_SWIM (0,5 m, 3 m ou 5 m), moyenne de ces pixels ; vide si l'indice de la cellule reste sous
    SEUIL_SWIM (pas de profondeur de glace à l'équateur). Hors du domaine (± 60°, sous +1 km) : NaN."""
    import rasterio
    cartes = {}
    for nom in BANDES_SWIM:
        f = CACHE / "swim" / f"SWIM2_{nom}.tif"
        if not telecharger(URL_SWIM.format(nom=nom), f):
            print("  SWIM indisponible : indice_glace_sol et profondeur_glace_m laissées vides")
            return np.full(len(cellules), np.nan, np.float32), np.full(len(cellules), np.nan, np.float32)
        with rasterio.open(f) as r:
            a, tr = r.read(1).astype(np.float32), r.transform
        a[(a < -50) | ~np.isfinite(a)] = np.nan                           # -100 : hors du domaine
        cartes[nom] = a
    ic0, ic1, ic5 = (cartes[k] for k in BANDES_SWIM)
    with np.errstate(invalid="ignore"):
        indice = np.fmax.reduce(np.clip(np.stack([ic0, ic1, ic5]), 0, 1), axis=0)     # NaN seulement si les trois le sont
        prof = np.full(indice.shape, np.nan, np.float32)
        for nom, ic in reversed(list(zip(BANDES_SWIM, (ic0, ic1, ic5)))):             # la tranche la moins profonde gagne
            prof = np.where(ic >= SEUIL_SWIM, BANDES_SWIM[nom], prof)
    m_par_deg = RAYON_KM["mars"] * 1000 * math.pi / 180
    lat_p = (tr.f + tr.e * (np.arange(indice.shape[0]) + 0.5)) / m_par_deg
    lon_p = (tr.c + tr.a * (np.arange(indice.shape[1]) + 0.5)) / m_par_deg
    bloc = 2                                                              # 0,1° : 6 km, une cellule fait ~9 km
    si, ni = somme_blocs(indice, bloc)
    sp, np_ = somme_blocs(prof, bloc)
    lat_b = lat_p[: si.shape[0] * bloc].reshape(-1, bloc).mean(axis=1)
    lon_b = lon_p[: si.shape[1] * bloc].reshape(-1, bloc).mean(axis=1)
    lon_b = (lon_b + 180) % 360 - 180
    r = accumuler(index, lat_b, lon_b, {"i_s": si, "i_n": ni, "p_s": sp, "p_n": np_}, res, zone, tous=True, lat_c=lat_c, lon_c=lon_c)
    print(f"  SWIM : {indice.shape[1]} × {indice.shape[0]} pixels, {int((r['i_n'] > 0).sum()):,} cellules renseignées")
    indice_c, prof_c = moyenne(r["i_s"], r["i_n"]), moyenne(r["p_s"], r["p_n"])
    with np.errstate(invalid="ignore"):
        prof_c[~(indice_c >= SEUIL_SWIM)] = np.nan                       # quelques pixels isolés ne suffisent pas
    return indice_c, prof_c


def grs_h2o(lat_c, lon_c) -> np.ndarray:
    """Eau équivalente (% massique) du premier mètre : Odyssey GRS, cases de 5° (lissées sur 10°)."""
    f = CACHE / "grs" / "h2o_sr_5x5.tab"
    if not telecharger(URL_GRS, f):
        print("  GRS indisponible : eau_sol_pct laissée vide")
        return np.full(len(lat_c), np.nan, np.float32)
    d = np.loadtxt(f, usecols=(0, 1, 2))
    grille = np.full((36, 72), np.nan, np.float32)                        # 5° : de -90 à 90, de 0 à 360 vers l'est
    i = np.floor((d[:, 0] + 90) / 5).astype(int)
    j = np.floor((d[:, 1] % 360) / 5).astype(int)
    grille[i, j] = np.where(d[:, 2] > 9000, np.nan, d[:, 2])             # 9999,999 : case sans valeur
    li = np.clip(np.floor((lat_c + 90) / 5).astype(int), 0, 35)
    ci = np.floor((np.asarray(lon_c) % 360) / 5).astype(int) % 72
    print(f"  GRS : {int(np.isfinite(grille).sum())} cases de 5° renseignées sur {grille.size}")
    return grille[li, ci]


def glace_perenne_mcd(dossier: Path, lat_c, lon_c) -> np.ndarray:
    """1 pour les points de la MCD (3,75° × 5,6°) où la glace d'eau de surface dépasse SEUIL_GLACE_MARS kg/m²
    tous les mois de l'année, 0 ailleurs ; NaN si la MCD n'est pas copiée (inputs/mcd)."""
    import xarray as xr
    fichiers = sorted(f for f in dossier.rglob("*_me.nc")
                      if "thermo" not in f.name.lower() and re.search(r"(\d{2})_?me\.nc$", f.name)) if dossier.is_dir() else []
    if len(fichiers) != 12:
        print(f"  MCD : {len(fichiers)} fichiers clim_??_me.nc dans {dossier} (12 attendus) : part_glace_surface laissée vide")
        return np.full(len(lat_c), np.nan, np.float32)
    mois = []
    for f in fichiers:
        with xr.open_dataset(f, decode_times=False) as ds:
            da = ds["h2oice"].isel(altitude=0) if "altitude" in ds["h2oice"].dims else ds["h2oice"]
            mois.append(da.transpose("Time", "latitude", "longitude").values.astype(np.float32).mean(axis=0))
            lat_m, lon_m = ds["latitude"].values.astype(float), ds["longitude"].values.astype(float)
    perenne = (np.min(mois, axis=0) > SEUIL_GLACE_MARS).astype(np.float32)
    print(f"  MCD : glace d'eau pérenne sur {int(perenne.sum())} points de grille")
    return sur_cellules(perenne, lat_m, lon_m, lat_c, lon_c)


# ------------------------------------------------------------------ Lune
def lune(args) -> None:
    print("\n=== Lune")
    res = args.resolution
    cellules, lat_c, lon_c = cellules_globales(res, args.zone)
    index = pd.Index(cellules)
    n = len(cellules)
    print(f"  {n:,} cellules H3 de résolution {res}")
    v, sources = {}, {}
    v["indice_glace_sol"], v["profondeur_glace_m"] = diviner_prp(index, cellules, res, args.zone)
    sources["glace_sol"] = "Diviner Polar Resource Product (Paige et al. 2010) : profondeur de la glace stable, au-delà de 80°"
    v["eau_sol_pct"] = lunar_prospector(lat_c, lon_c)
    sources["eau_sol"] = "Lunar Prospector, hydrogène (ppm massiques, Feldman et al. 2001) x 8,94 = eau équivalente"
    v["part_glace_surface"] = glace_exposee_lune(index, res, args.zone)
    sources["glace_surface"] = "M3, glace exposée (Li et al. 2018) : base de Lemelin et al. 2021 (Zenodo 4646092), pôle sud seulement"
    v["part_ombre_permanente"] = ombres_permanentes(index, lat_c, lon_c, res, args.zone)
    sources["ombre_permanente"] = "LOLA, cartes des ombres permanentes à 240 m, 65° à 90° (Mazarico et al. 2011)"
    v["part_eau_libre"] = np.zeros(n, np.float32)                         # pas d'eau liquide
    ecrire("moon", res, assembler("moon", res, cellules, v), sources)


def glace_exposee_lune(index, res: int, zone):
    """Glace d'eau exposée en surface vue par M3 (Li et al. 2018), pôle sud seulement : base de Lemelin et al. 2021, 169
    ombres permanentes où M3 a détecté de la glace (nombre de pixels de 280 m par région). Le nombre de pixels de
    chaque région est réparti entre les cellules qu'elle recouvre, au prorata de la surface (sous-cellules H3 de
    résolution res + 3). Part = surface de pixels M3 / surface de la cellule. 0 plus loin que LAT_M3_SUD vers le
    pôle sud (M3 y a cherché sans rien trouver), vide ailleurs (pôle nord et basses latitudes : pas de base)."""
    import geopandas as gpd
    n = len(index)
    f = CACHE / "lemelin" / "Lemelin_2021_south_pole_ROIs.zip"
    if not telecharger(URL_LEMELIN, f):
        print("  Lemelin et al. 2021 indisponible : part_glace_surface laissée vide")
        return np.full(n, np.nan, np.float32)
    dossier = f.with_suffix("")
    if not dossier.is_dir():
        with zipfile.ZipFile(f) as z:
            z.extractall(dossier)
    gdf = gpd.read_file(sorted(dossier.glob("*.shp"))[0])
    gdf = gdf.to_crs(gdf.crs.geodetic_crs)
    km2 = np.zeros(n)
    for geom, pixels, lat0, lon0 in zip(gdf.geometry, gdf["Count_M3"], gdf["Latitude"], gdf["Longitude"]):
        if zone and not dans_zone([lat0], [lon0], zone)[0]:
            continue
        fines = [h3.cell_to_parent(c, res) for c in h3.geo_to_cells(geom, res + 3)]
        parents = pd.Series(fines if fines else [h3.latlng_to_cell(lat0, lon0, res)]).value_counts()
        pos = index.get_indexer(parents.index)
        ok = pos >= 0
        np.add.at(km2, pos[ok], pixels * PIXEL_M3_KM2 * parents.to_numpy()[ok] / parents.sum())
    avec = km2 > 0
    part = np.zeros(n)
    part[avec] = km2[avec] / aire_cellules(index[avec], "moon")
    lat_c = np.array([h3.cell_to_latlng(c)[0] for c in index])
    resultat = np.where(lat_c <= LAT_M3_SUD, np.clip(part, 0, 1), np.nan).astype(np.float32)
    print(f"  M3 (Lemelin) : {len(gdf)} ombres, {int(gdf['Count_M3'].sum())} pixels de glace, {int(avec.sum()):,} cellules concernées")
    return resultat


def diviner_prp(index, cellules, res, zone):
    """Produit Diviner des ressources polaires : maillage de triangles de ~0,1 km² au-delà de 80°. Indice = part
    de la surface où la glace d'eau est stable de la surface à 2,87 m de profondeur (ice_depth >= 0, ou -1 pour les
    pièges froids ; -999 : non stable) ; profondeur = moyenne là où elle l'est (ice_depth : profondeur où la glace se sublime à 1 kg/m² par
    milliard d'années).
    Une cellule couverte à moins de COUVERTURE_PRP_MIN par le maillage reste vide."""
    n = len(index)
    nan = np.full(n, np.nan, np.float32)
    aire_tot, aire_glace, prof_aire = np.zeros(n), np.zeros(n), np.zeros(n)
    for pole in ("north", "south"):
        f = CACHE / "diviner_prp" / f"dlre_prp_{pole}.tab"
        verifier_espace(f.parent, 1.5, "le produit Diviner des ressources polaires")
        if not telecharger(URL_PRP.format(pole=pole), f):
            print("  Diviner PRP indisponible : indice_glace_sol et profondeur_glace_m laissées vides")
            return nan, nan
        t0 = time.time()
        cols = ["tri1_x", "tri1_y", "tri1_z", "tri2_x", "tri2_y", "tri2_z", "tri3_x", "tri3_y", "tri3_z", "tri_clon", "tri_clat", "ice_depth"]
        for morceau in pd.read_csv(f, usecols=cols, skipinitialspace=True, chunksize=500_000):
            if zone:
                morceau = morceau[dans_zone(morceau["tri_clat"], morceau["tri_clon"], zone)]
            if morceau.empty:
                continue
            p1 = morceau[["tri1_x", "tri1_y", "tri1_z"]].to_numpy()
            p2 = morceau[["tri2_x", "tri2_y", "tri2_z"]].to_numpy()
            p3 = morceau[["tri3_x", "tri3_y", "tri3_z"]].to_numpy()
            aire = 0.5 * np.linalg.norm(np.cross(p2 - p1, p3 - p1), axis=1)            # km² (coordonnées en km)
            pos = index.get_indexer(vers_cellules(morceau["tri_clat"], morceau["tri_clon"], res))
            ok = pos >= 0
            profondeur = morceau["ice_depth"].to_numpy()
            # -999 : pas stable à moins de 2,87 m. -1 (non documenté) : triangles dont le maximum thermique est de
            # ~77 K en médiane, les pièges froids : la glace y est stable en surface, comme à 0 m.
            glace = (profondeur >= 0) | (profondeur == -1)
            profondeur = np.where(profondeur == -1, 0.0, profondeur)
            aire_tot += np.bincount(pos[ok], weights=aire[ok], minlength=n)
            aire_glace += np.bincount(pos[ok], weights=(aire * glace)[ok], minlength=n)
            prof_aire += np.bincount(pos[ok], weights=(aire * glace * np.where(glace, profondeur, 0))[ok], minlength=n)
        print(f"  Diviner PRP {pole} lu ({time.time() - t0:.0f} s)")
    couvert = np.zeros(n)
    avec = aire_tot > 0
    couvert[avec] = aire_tot[avec] / aire_cellules(index[avec], "moon")
    valide = couvert >= COUVERTURE_PRP_MIN
    indice = np.where(valide, aire_glace / np.maximum(aire_tot, 1e-12), np.nan).astype(np.float32)
    profondeur = np.where(valide & (aire_glace > 0), prof_aire / np.maximum(aire_glace, 1e-12), np.nan).astype(np.float32)
    print(f"  Diviner PRP : {int(valide.sum()):,} cellules renseignées, {int(np.nansum(indice > 0)):,} avec de la glace stable")
    return indice, profondeur


def lunar_prospector(lat_c, lon_c) -> np.ndarray:
    """Hydrogène de Lunar Prospector (ppm massiques, cases de 0,5°) converti en eau équivalente (% massique)."""
    f = CACHE / "lunar_prospector" / "hydrogenhd.txt"
    if not telecharger(URL_LP, f):
        print("  Lunar Prospector indisponible : eau_sol_pct laissée vide")
        return np.full(len(lat_c), np.nan, np.float32)
    d = pd.read_csv(f, comment="#", header=None, skipinitialspace=True, dtype=str).apply(pd.to_numeric, errors="coerce").to_numpy()
    grille = np.full((360, 720), np.nan, np.float32)                      # de -90 à 90, de -180 à 180
    i = np.clip(np.floor((d[:, 0] + 90) / 0.5).astype(int), 0, 359)
    j = np.clip(np.floor((d[:, 2] + 180) / 0.5).astype(int), 0, 719)
    ppm = np.where(np.isfinite(d[:, 4]) & (d[:, 4] > -100), d[:, 4], np.nan)           # « ********** » : case sans valeur
    grille[i, j] = np.clip(ppm, 0, None) * H2O_PAR_H / 1e4                # ppm -> %
    li = np.clip(np.floor((lat_c + 90) / 0.5).astype(int), 0, 359)
    ci = np.clip(np.floor((np.asarray(lon_c) + 180) / 0.5).astype(int), 0, 719)
    print(f"  Lunar Prospector : hydrogène {np.nanmin(ppm):.0f} à {np.nanmax(ppm):.0f} ppm")
    return grille[li, ci]


def ombres_permanentes(index, lat_c, lon_c, res, zone) -> np.ndarray:
    """Part de chaque cellule en ombre permanente (LOLA, pixels de 240 m) entre 65° et 90° ; 0 plus bas, où
    la carte ne s'étend pas (aucune ombre permanente connue à ces latitudes)."""
    import rasterio
    from pyproj import CRS, Transformer
    n = len(index)
    part = np.zeros(n)
    for h in "NS":
        f = CACHE / "lola_psr" / f"LPSR_65{h}_240M_201608.TIF"
        if not telecharger(URL_PSR.format(h=h), f):
            print(f"  LOLA PSR {h} indisponible : part_ombre_permanente laissée à 0 sur ce pôle")
            continue
        with rasterio.open(f) as r:
            a, tr, crs = r.read(1), r.transform, CRS.from_wkt(r.crs.to_wkt())
        ombre = (a == 20000).astype(np.float32)
        s, nb = somme_blocs(ombre, 4)                                     # blocs de 960 m
        x = tr.c + tr.a * (np.arange(s.shape[1]) * 4 + 2)
        y = tr.f + tr.e * (np.arange(s.shape[0]) * 4 + 2)
        X, Y = np.meshgrid(x, y)
        lon, lat = Transformer.from_crs(crs, crs.geodetic_crs, always_xy=True).transform(X.ravel(), Y.ravel())
        lat, lon = np.asarray(lat), np.asarray(lon)
        garde = (lat >= 65) if h == "N" else (lat <= -65)
        if zone:
            garde &= dans_zone(lat, lon, zone)
        pos = index.get_indexer(vers_cellules(lat[garde], lon[garde], res))
        ok = pos >= 0
        somme = np.bincount(pos[ok], weights=s.ravel()[garde][ok], minlength=n)
        blocs = np.bincount(pos[ok], weights=nb.ravel()[garde][ok], minlength=n)
        avec = blocs > 0
        part[avec] = somme[avec] / blocs[avec]
        print(f"  LOLA PSR {h} : {int((ombre > 0).sum() * 0.0576):,} km² d'ombre permanente, {int((part > 0).sum()):,} cellules concernées")
    return part.astype(np.float32)


def main() -> int:
    args = options()
    t0 = time.time()
    for corps, fonction in (("moon", lune), ("mars", mars), ("earth", terre)):
        if corps in args.corps:
            (maj_glace if args.glace_seulement and corps == "earth" else fonction)(args)
    print(f"\nTerminé en {(time.time() - t0) / 60:.1f} min.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
