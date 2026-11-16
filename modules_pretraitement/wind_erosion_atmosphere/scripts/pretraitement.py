"""Wind Dynamics, Erosion, and Atmosphere module: Earth and Mars preprocessing.

    python modules_pretraitement/wind_erosion_atmosphere/scripts/pretraitement.py                       # Both celestial bodies
    python modules_pretraitement/wind_erosion_atmosphere/scripts/pretraitement.py --corps mars          # All options: --help

One row per H3 cell (resolution 5 by default; on Earth, only land cells),
written to pretreatment_data/wind_erosion_atmosphere/.

Raw physical quantities cannot be directly compared between celestial bodies
(Mars' atmosphere is approximately 60 times less dense than Earth's).
Therefore, the feature vector contains ratios relative to each body's
saltation threshold and within-body rankings.

Both celestial bodies follow the same definitions (see the module README).

Data Sources
  Earth  NASA MERRA-2 M2TUNXFLX (friction velocity and air density,
         monthly × hourly averages),
         NASA MERRA-2 M2TMNXAER (dust optical depth),
         NASA VIIRS Deep Blue AERDB_D3_VIIRS_SNPP
         (daily aerosol observations, "dust" aerosol type),
         NASA MODIS MCD12C1 (bare ground),
         Gunn (2026) global dune map (MIT license).

  Mars   Mars Climate Database v6.2 (LMD),
         Montabone et al. (2015) dust climatology,
         Mars Global Digital Dune Database (MGD3, USGS).
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import time
import urllib.request
from pathlib import Path

import h3
import numpy as np
import pandas as pd

RACINE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RACINE / "scripts"))
from commun import court, reconstruire_duckdb  # noqa: E402
MODULE = "wind_erosion_atmosphere"
SORTIE = RACINE / "pretreatment_data" / MODULE
CACHE = RACINE / "cache" / MODULE
ENTREES = RACINE / "inputs" / MODULE

# --- Seuil de mise en saltation (Shao et Lu 2000) : u*t = √(A_N (ρ_grain/ρ_air g d + γ / (ρ_air d)))
A_N, GAMMA = 0.0123, 3e-4
DIAMETRE_GRAIN = 100e-6                   # m, autour du diamètre le plus facile à mettre en mouvement
PHYSIQUE = {"earth": {"gravite": 9.81, "rho_grain": 2650.0},    # sable de quartz
            "mars": {"gravite": 3.71, "rho_grain": 3000.0}}     # sable basaltique

# --- Vitesse de frottement sur sol nu, même calcul sur les deux corps : profil logarithmique en atmosphère
# neutre, u* = 0,4 × vent au niveau le plus bas du modèle / ln(z / z0), z0 = 1 cm (rugosité de la MCD).
# Sur Terre, USTAR de MERRA-2 inclut la rugosité de la végétation et des villes : sous une forêt il est
# fort alors qu'aucun grain ne bouge. On recalcule donc u* comme si le sol était nu.
KARMAN, Z0_SOL = 0.4, 0.01

# --- Mars
SEUIL_GLACE = 1.0                         # kg/m² de givre de CO2 ou de glace d'eau : surface non nue
VISIBLE_PAR_CDOD = 2.6                    # absorption 9,3 µm -> extinction visible (Montabone)
URL_MONTABONE = "https://www-mars.lmd.jussieu.fr/mars/dust_climatology/dataset_v2/dustscenario_MY{my}_v{v}.nc"
VERSIONS_MONTABONE = {**{my: "2-0" for my in range(24, 33)}, 33: "2-1", 34: "2-5", 35: "2-5", 36: "2-5"}

# --- Terre : carte mondiale des dunes au 0,1° (Gunn 2026, Nature Communications ; licence MIT)
URL_DUNES_TERRE = "https://github.com/geomorphlab/dune-world/raw/main/dune-mask-rev1.tif"

# --- Commun
SEUIL_TEMPETE = 1.0                       # épaisseur optique visible de la poussière au-delà de laquelle un jour compte comme tempête

COLONNES = ["vent_fort_rel", "part_dunes", "part_sol_nu", "poussiere_rang", "tempetes_rang",
            "u_etoile_p95", "u_etoile_seuil", "densite_air", "poussiere_opacite", "tempetes_freq",
            "couverture", "fiabilite"]
INDICATEURS = ["vent_fort_rel", "part_dunes", "part_sol_nu", "poussiere_rang", "tempetes_rang"]
SITES = {
    "earth": {"Sahara (Bodélé)": (17.0, 18.0), "Namib (mer de sable)": (-24.7, 15.3), "Atacama": (-24.5, -69.25),
              "Death Valley": (36.46, -116.87), "Vallées sèches (Antarctique)": (-77.5, 162.0), "Montréal": (45.5, -73.57)},
    "mars": {"Gale (dunes Bagnold)": (-4.59, 137.44), "Olympia Undae (erg polaire)": (81.0, 180.0),
             "Hellas": (-42.4, 70.5), "Olympus Mons": (18.65, -133.8), "Meridiani": (-1.95, -5.53),
             "Jezero": (18.44, 77.45), "Pôle sud": (-87.0, 0.0)},
}


# ------------------------------------------------------------------ outils communs
def options() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--corps", nargs="+", choices=("earth", "mars"), default=["earth", "mars"])
    p.add_argument("--resolution", type=int, default=5, help="résolution H3 (défaut : 5)")
    p.add_argument("--dunes-seulement", action="store_true",
                   help="recalculer seulement part_dunes dans les résultats déjà écrits (rien n'est retéléchargé)")
    p.add_argument("--seuil-tempete", type=float, default=SEUIL_TEMPETE,
                   help=f"épaisseur optique visible de la poussière d'un jour de tempête (défaut : {SEUIL_TEMPETE})")
    g = p.add_argument_group("Terre")
    g.add_argument("--annee", type=int, default=2023, help="année des données (défaut : 2023)")
    g.add_argument("--zone", type=float, nargs=4, metavar=("OUEST", "SUD", "EST", "NORD"),
                   help="limiter la Terre à une boîte lat/lon (calcul plus court, même téléchargement)")
    g.add_argument("--dunes-terre", type=Path, default=ENTREES / "dunes_terre",
                   help=f"dossier d'une autre carte des dunes (contours ou GeoTIFF) ; vide : carte mondiale "
                        f"de Gunn (2026), téléchargée (défaut : inputs/{MODULE}/dunes_terre)")
    g = p.add_argument_group("Mars")
    g.add_argument("--mcd", type=Path, default=RACINE / "inputs" / "mcd", help="dossier de la MCD (défaut : inputs/mcd)")
    g.add_argument("--mgd3", type=Path, default=ENTREES / "mgd3", help=f"dossier de la MGD3 (défaut : inputs/{MODULE}/mgd3)")
    g.add_argument("--annees-mars", type=int, nargs="+", default=list(VERSIONS_MONTABONE),
                   help="années martiennes de Montabone (défaut : 24 à 36)")
    return p.parse_args()


def seuil_saltation(corps: str, rho_air: np.ndarray) -> np.ndarray:
    ph = PHYSIQUE[corps]
    return np.sqrt(A_N * (ph["rho_grain"] / rho_air * ph["gravite"] * DIAMETRE_GRAIN + GAMMA / (rho_air * DIAMETRE_GRAIN)))


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


def rang(x) -> np.ndarray:
    """Rang parmi les cellules du corps, de 0 (la plus faible) à 1 (la plus forte) : part des autres
    cellules strictement plus faibles. Les ex aequo ont le même rang (toutes les cellules sans tempête : 0,
    et non le rang moyen de 0,41) ; NaN reste NaN."""
    s = pd.Series(np.asarray(x, dtype=float))
    n = s.notna().sum()
    return ((s.rank(method="min") - 1) / max(n - 1, 1)).to_numpy(dtype=np.float32)


def vers_cellules(lats, lngs, res: int) -> np.ndarray:
    return np.array([h3.latlng_to_cell(float(a), float(b), res) for a, b in zip(lats, lngs)])


def part_dunes(fichiers: list[Path], cellules: np.ndarray, lat_c: np.ndarray, res: int, emprise) -> np.ndarray:
    """Part de chaque cellule couverte de champs de dunes : sous-cellules H3 (res + 3, 343 par cellule)
    dont le centre tombe dans un polygone. Hors de l'emprise des fichiers : NaN (inconnu, pas 0).
    emprise(gdf) -> (latitude min, latitude max) couverte par le fichier."""
    nan = np.full(len(cellules), np.nan, dtype=np.float32)
    if not fichiers:
        return nan
    import geopandas as gpd
    fines, bandes, vus = set(), [], set()
    for f in fichiers:
        gdf = gpd.read_file(f)
        gdf = gdf[gdf.geometry.notna() & gdf.geom_type.isin(["Polygon", "MultiPolygon"])]
        if gdf.empty:
            continue
        if gdf.crs is not None and gdf.crs.is_projected:
            gdf = gdf.to_crs(gdf.crs.geodetic_crs)                        # vers longitude/latitude du corps
        gdf = gdf.explode(index_parts=False)
        signature = (f.name, len(gdf), tuple(np.round(gdf.total_bounds, 1)))
        if signature in vus:                                              # même couche livrée en deux projections
            print(f"  dunes : {f.relative_to(f.parents[1])} identique à une couche déjà lue, ignoré")
            continue
        vus.add(signature)
        bandes.append(emprise(gdf))
        for geom in gdf.geometry:
            fines.update(h3.geo_to_cells(geom, res + 3))
        b = gdf.total_bounds
        print(f"  dunes : {f.name}, {len(gdf)} polygones, latitudes {b[1]:.1f} à {b[3]:.1f}")
    if not bandes:
        print("  dunes : aucun polygone lu, part_dunes laissée vide")
        return nan
    parents = pd.Series([h3.cell_to_parent(c, res) for c in fines], dtype=object).value_counts()
    part = pd.Series(cellules).map(parents).fillna(0).to_numpy(dtype=np.float32) / 7 ** 3
    couvert = np.zeros(len(cellules), dtype=bool)
    for bas, haut in bandes:
        couvert |= (lat_c >= bas) & (lat_c <= haut)
    part[~couvert] = np.nan
    print(f"  dunes : {int(np.nansum(part > 0)):,} cellules avec des dunes, emprise {couvert.mean():.0%} des cellules")
    return np.clip(part, 0, 1)


def fichiers_dunes(dossier: Path) -> list[Path]:
    tous = [f for f in sorted(dossier.rglob("*")) if f.suffix.lower() in (".shp", ".gml", ".gpkg", ".geojson")] if dossier.is_dir() else []
    choisis = [f for f in tous if "dune" in f.stem.lower() and "field" in f.stem.lower()]
    return choisis or [f for f in tous if "dune" in f.stem.lower()] or tous


def ecrire(corps: str, res: int, cellules, v: dict) -> None:
    t = pd.DataFrame({"body": corps, "resolution": res, "h3": cellules})
    t["vent_fort_rel"] = (v["u_etoile_p95"] / v["u_etoile_seuil"]).astype(np.float32)
    t["part_dunes"] = np.asarray(v["part_dunes"], dtype=np.float32)
    t["part_sol_nu"] = np.asarray(v["part_sol_nu"], dtype=np.float32)
    t["poussiere_rang"] = rang(v["poussiere_opacite"])
    t["tempetes_rang"] = rang(v["tempetes_freq"])
    for c in ("u_etoile_p95", "u_etoile_seuil", "densite_air", "poussiere_opacite", "tempetes_freq"):
        t[c] = np.asarray(v[c], dtype=np.float32)
    sauver(corps, res, t)


def sauver(corps: str, res: int, t: pd.DataFrame) -> None:
    t["couverture"] = t[INDICATEURS].notna().mean(axis=1).astype(np.float32)
    t["fiabilite"] = t["couverture"]                                       # provisoire, même règle que thermal
    t = t[["body", "resolution", "h3", *COLONNES]]
    SORTIE.mkdir(parents=True, exist_ok=True)
    nom = f"{MODULE}_{corps}_h3_{res}"
    chemin = SORTIE / f"{nom}.parquet"
    t.to_parquet(chemin, index=False, compression="zstd")
    reconstruire_duckdb(SORTIE, corps)                          # copie des Parquet, refaite entièrement
    print(f"{corps} : {len(t):,} cellules écrites dans {court(chemin, RACINE)}")

    ti = t.set_index("h3")
    lignes = []
    for s, (la, lo) in SITES[corps].items():
        c = h3.latlng_to_cell(la, lo, res)
        lignes.append({"site": s, **(ti.loc[c, INDICATEURS + ["u_etoile_p95", "u_etoile_seuil"]].to_dict()
                                     if c in ti.index else {"remarque": "hors des cellules"})})
    with pd.option_context("display.width", 250, "display.max_columns", None):
        print(pd.DataFrame(lignes).round(3).to_string(index=False))
        print(t[INDICATEURS + ["u_etoile_p95", "u_etoile_seuil", "densite_air", "couverture"]].describe().round(3).to_string())


# ------------------------------------------------------------------ Terre
def connexion_earthdata():
    import earthaccess
    if not earthaccess.login().authenticated:
        sys.exit("Connexion NASA Earthdata impossible : identifiant dans ~/.netrc, ou EARTHDATA_USERNAME et EARTHDATA_PASSWORD dans .env")
    return earthaccess


def chercher(ea, nom_court: str, annee: int, version: str | None = None) -> list:
    kw = {"short_name": nom_court, "temporal": (f"{annee}-01-01", f"{annee}-12-31")}
    if version:
        kw["version"] = version
    g = ea.search_data(**kw)
    print(f"  {nom_court} : {len(g)} fichiers")
    return g


def un_par_un(ea, granules, dossier: Path, lire):
    """Télécharge, lit puis efface chaque fichier : le disque ne garde qu'un fichier à la fois."""
    dossier.mkdir(parents=True, exist_ok=True)
    for k, g in enumerate(granules):
        try:
            telecharges = ea.download([g], local_path=str(dossier), show_progress=False)
        except TypeError:                                                 # anciennes versions d'earthaccess
            telecharges = ea.download([g], local_path=str(dossier))
        if not telecharges:
            print(f"    téléchargement impossible : {g}")
            continue
        chemin = Path(telecharges[0])
        try:
            yield lire(chemin)
        finally:
            chemin.unlink(missing_ok=True)
        if (k + 1) % 25 == 0 or k + 1 == len(granules):
            print(f"    {k + 1}/{len(granules)}")


def terre(args) -> None:
    print("\n=== Terre")
    ea = connexion_earthdata()
    res = args.resolution

    # --- MODIS MCD12C1 : terres émergées et part de sol nu (classe IGBP 16, « Barren »)
    from pyhdf.SD import SD, SDC
    def lire_mcd12(chemin):
        sd = SD(str(chemin), SDC.READ)
        s = sd.select("Land_Cover_Type_1_Percent")
        axe = list(s.info()[2]).index(17)                                # axe des 17 classes IGBP
        prendre = lambda k: s[tuple(k if i == axe else slice(None) for i in range(3))]
        eau, nu = prendre(0).astype(np.float32), prendre(16).astype(np.float32)
        sd.end()
        return eau, nu
    g = chercher(ea, "MCD12C1", args.annee, "061") or chercher(ea, "MCD12C1", args.annee - 1, "061")
    lu = list(un_par_un(ea, g[:1], CACHE / "mcd12c1", lire_mcd12))
    if not lu:
        print("  MCD12C1 introuvable : Terre ignorée")
        return
    eau, nu = lu[0]
    n_lat, n_lon = eau.shape
    pas = 180.0 / n_lat
    lig, col = np.nonzero(eau < 50)                                       # pixels majoritairement terrestres
    pix_lat, pix_lon = 90 - pas * (lig + 0.5), -180 + pas * (col + 0.5)
    sol_nu_pix = nu[lig, col] / np.maximum(100 - eau[lig, col], 1)
    del eau, nu
    if args.zone:
        o, s_, e, n = args.zone
        garde = (pix_lon >= o) & (pix_lon <= e) & (pix_lat >= s_) & (pix_lat <= n)
        pix_lat, pix_lon, sol_nu_pix = pix_lat[garde], pix_lon[garde], sol_nu_pix[garde]
    t0 = time.time()
    cell_pix = vers_cellules(pix_lat, pix_lon, res)
    cellules, inverse = np.unique(cell_pix, return_inverse=True)
    sol_nu = np.bincount(inverse, weights=sol_nu_pix) / np.bincount(inverse)
    centres = np.array([h3.cell_to_latlng(c) for c in cellules])
    lat_c, lon_c = centres[:, 0], centres[:, 1]
    print(f"  {len(cellules):,} cellules de terre, sol nu calculé ({time.time() - t0:.0f} s)")

    # --- MERRA-2 M2TUNXFLX : vent au niveau le plus bas et densité de l'air, moyennes mois × heure
    import xarray as xr
    def lire_flx(chemin):
        with xr.open_dataset(chemin) as ds:
            if all(v in ds for v in ("ULML", "VLML", "HLML")):           # vent à ~60 m -> u* sur sol nu
                vent = np.hypot(ds["ULML"].values, ds["VLML"].values)
                hauteur = np.maximum(ds["HLML"].values, 2.0)
                u = (KARMAN * vent / np.log(hauteur / Z0_SOL)).astype(np.float32)
            else:
                print("  ULML/VLML/HLML absents : USTAR de MERRA-2 (rugosité réelle, végétation comprise)")
                u = ds["USTAR"].values.astype(np.float32)
            return u, ds["RHOA"].values.astype(np.float32).mean(axis=0), ds["lat"].values, ds["lon"].values
    ustar, rho = [], []
    for u, r, lat_m, lon_m in un_par_un(ea, chercher(ea, "M2TUNXFLX", args.annee), CACHE / "merra2", lire_flx):
        ustar.append(u); rho.append(r)
    if not ustar:
        print("  M2TUNXFLX introuvable : Terre ignorée")
        return
    u_p95 = np.percentile(np.concatenate(ustar), 95, axis=0)             # 12 mois × 24 heures
    rho_m = np.mean(rho, axis=0)
    del ustar
    grille = lambda c: sur_cellules(c, lat_m, lon_m, lat_c, lon_c)
    u_p95_c, rho_c = grille(u_p95), grille(rho_m)

    # --- MERRA-2 M2TMNXAER : épaisseur optique des poussières à 550 nm, moyenne annuelle
    def lire_aer(chemin):
        with xr.open_dataset(chemin) as ds:
            return ds["DUEXTTAU"].values.astype(np.float32).mean(axis=0)
    aod = np.mean(list(un_par_un(ea, chercher(ea, "M2TMNXAER", args.annee), CACHE / "merra2", lire_aer)), axis=0)
    poussiere = grille(aod)

    # --- VIIRS Deep Blue quotidien (1°) : jours où la poussière domine et dépasse le seuil
    try:
        tempetes = viirs_tempetes(ea, args, lat_c, lon_c)
    except (KeyError, ValueError, OSError) as e:                       # ne pas perdre le reste du calcul
        print(f"  VIIRS illisible ({e}) : tempetes_* laissées vides")
        tempetes = np.full(len(cellules), np.nan)

    dunes = dunes_terre(args, cellules, lat_c)

    ecrire("earth", res, cellules,
           {"u_etoile_p95": u_p95_c, "u_etoile_seuil": seuil_saltation("earth", rho_c), "densite_air": rho_c,
            "part_dunes": dunes, "part_sol_nu": sol_nu, "poussiere_opacite": poussiere, "tempetes_freq": tempetes})


def dunes_terre(args, cellules, lat_c) -> np.ndarray:
    """Contours ou GeoTIFF fournis dans --dunes-terre ; sinon la carte mondiale de Gunn (2026)."""
    vecteurs = fichiers_dunes(args.dunes_terre)
    if vecteurs:
        return part_dunes(vecteurs, cellules, lat_c, args.resolution,
                          lambda gdf: (float(gdf.total_bounds[1]), float(gdf.total_bounds[3])))
    rasters = sorted(args.dunes_terre.glob("*.tif")) if args.dunes_terre.is_dir() else []
    if rasters:
        return part_dunes_raster(rasters[0], cellules, args.resolution)
    cible = CACHE / "dunes_terre" / Path(URL_DUNES_TERRE).name
    if not cible.is_file():
        cible.parent.mkdir(parents=True, exist_ok=True)
        partiel = cible.with_suffix(".part")
        try:
            urllib.request.urlretrieve(URL_DUNES_TERRE, partiel)
            if partiel.read_bytes()[:4] not in (b"II*\x00", b"MM\x00*"):
                raise OSError("le fichier reçu n'est pas un GeoTIFF")
            partiel.replace(cible)
            print(f"  dunes : carte mondiale de Gunn (2026) téléchargée ({cible.stat().st_size / 1e6:.0f} Mo)")
        except OSError as e:
            partiel.unlink(missing_ok=True)
            print(f"  dunes : téléchargement impossible ({e}) ; mettre dune-mask-rev1.tif dans {args.dunes_terre}")
            return np.full(len(cellules), np.nan, dtype=np.float32)
    return part_dunes_raster(cible, cellules, args.resolution)


def part_dunes_raster(chemin: Path, cellules: np.ndarray, res: int) -> np.ndarray:
    """Part de chaque cellule couverte de dunes, d'après une grille 0/1 en longitude/latitude :
    surface des pixels de dunes dont le centre tombe dans la cellule / surface de la cellule."""
    import rasterio
    with rasterio.open(chemin) as r:
        a, tr = r.read(1), r.transform
    lig, col = np.nonzero(np.nan_to_num(a, nan=0.0) >= 0.5)
    lon = tr.c + tr.a * (col + 0.5)
    lat = tr.f + tr.e * (lig + 0.5)
    garde = np.abs(lat) < 90
    lat, lon = lat[garde], lon[garde]
    rayon = 6371.0088                                                      # km, comme h3.cell_area
    d_lon, d_lat = math.radians(abs(tr.a)), math.radians(abs(tr.e))
    surface = rayon ** 2 * d_lon * np.abs(np.sin(np.radians(lat) + d_lat / 2) - np.sin(np.radians(lat) - d_lat / 2))
    par_cellule = pd.Series(surface).groupby(vers_cellules(lat, lon, res)).sum()
    aire = np.array([h3.cell_area(c, unit="km^2") for c in cellules])
    part = pd.Series(cellules).map(par_cellule).fillna(0).to_numpy() / aire
    print(f"  dunes : {chemin.name}, {len(lat):,} pixels de dunes, {int((part > 0).sum()):,} cellules avec des dunes")
    return np.clip(part, 0, 1).astype(np.float32)


def viirs_tempetes(ea, args, lat_c, lon_c) -> np.ndarray:
    import xarray as xr
    granules = chercher(ea, "AERDB_D3_VIIRS_SNPP", args.annee)
    par_jour = {}                                                         # une version par jour, la plus récente
    for g in granules:
        nom = Path(str(g.data_links()[0])).name
        jour = re.search(r"\.A(\d{7})\.", nom)
        if jour and (jour.group(1) not in par_jour or nom > par_jour[jour.group(1)][0]):
            par_jour[jour.group(1)] = (nom, g)
    granules = [g for _, g in sorted(par_jour.values(), key=lambda x: x[0])]
    etat = {}

    def lire(chemin):
        with xr.open_dataset(chemin) as ds:
            aot = ds["Aerosol_Optical_Thickness_550_Land_Ocean_Mean"]
            typ = ds["Aerosol_Type_Land_Ocean_Mode"]
            if "code_poussiere" not in etat:
                valeurs = np.atleast_1d(typ.attrs.get("flag_values", []))
                sens = str(typ.attrs.get("flag_meanings", "")).lower().split()
                etat["code_poussiere"] = int(valeurs[sens.index("dust")]) if "dust" in sens and len(valeurs) == len(sens) else 0
                etat["lat"], etat["lon"] = axe_viirs(ds, "lat", aot.shape[0]), axe_viirs(ds, "lon", aot.shape[1])
                print(f"    VIIRS : code « poussière » = {etat['code_poussiere']}, grille {aot.shape}")
            a, t = aot.values.astype(np.float32), typ.values
        valide = np.isfinite(a)
        return valide, valide & (t == etat["code_poussiere"]) & (a >= args.seuil_tempete)

    jours = tempetes = None
    for valide, tempete in un_par_un(ea, granules, CACHE / "viirs", lire):
        jours = valide.astype(np.int32) if jours is None else jours + valide
        tempetes = tempete.astype(np.int32) if tempetes is None else tempetes + tempete
    if jours is None:
        print("    VIIRS : aucun fichier lu, tempetes_* laissées vides")
        return np.full(len(lat_c), np.nan)
    freq = np.where(jours > 0, tempetes / np.maximum(jours, 1), np.nan)
    return sur_cellules(freq, etat["lat"], etat["lon"], lat_c, lon_c)


def axe_viirs(ds, debut: str, taille: int) -> np.ndarray:
    """Latitudes ou longitudes de la grille VIIRS : variable 1D (« Latitude_1D »...) ou 2D."""
    noms = [v for v in ds.variables if v.lower().startswith(debut)]
    for v in sorted(noms, key=lambda v: ds[v].ndim):
        a = np.asarray(ds[v].values, dtype=float)
        if a.ndim == 1 and a.size == taille:
            return a
        if a.ndim == 2:
            a = a[:, 0] if debut == "lat" else a[0, :]
            if a.size == taille:
                return a
    raise ValueError(f"VIIRS : axe « {debut} » de {taille} valeurs introuvable ({list(ds.variables)})")


# ------------------------------------------------------------------ Mars
def mars(args) -> None:
    print("\n=== Mars")
    import xarray as xr
    res = args.resolution
    cellules = np.array([c for r0 in h3.get_res0_cells() for c in h3.cell_to_children(r0, res)])
    centres = np.array([h3.cell_to_latlng(c) for c in cellules])
    lat_c, lon_c = centres[:, 0], centres[:, 1]
    print(f"  {len(cellules):,} cellules H3 de résolution {res}")

    # --- MCD : vent et densité au niveau le plus bas, givre et glace, pression de surface
    fichiers = sorted(f for f in args.mcd.rglob("*_me.nc")
                      if "thermo" not in f.name.lower() and re.search(r"(\d{2})_?me\.nc$", f.name))
    if len(fichiers) != 12:
        print(f"  MCD : {len(fichiers)} fichiers clim_??_me.nc dans {args.mcd} (12 attendus) : Mars ignoré. "
              "Voir modules_pretraitement/wind_erosion_atmosphere/README.md")
        return
    champs = {k: [] for k in ("u", "v", "rho", "co2ice", "h2oice")}
    for f in fichiers:
        with xr.open_dataset(f, decode_times=False) as ds:
            for k in champs:
                da = ds[k].isel(altitude=0) if "altitude" in ds[k].dims else ds[k]
                champs[k].append(da.transpose("Time", "latitude", "longitude").values.astype(np.float32))
            if f == fichiers[0]:
                z = float(ds["altitude"].values[0]) * 1000.0
                lat_m, lon_m = ds["latitude"].values.astype(float), ds["longitude"].values.astype(float)
    c = {k: np.stack(v) for k, v in champs.items()}                        # (mois, heure, lat, lon)
    print(f"  MCD : 12 mois × {c['u'].shape[1]} heures, grille {len(lat_m)} × {len(lon_m)}, vent à {z:.1f} m")
    u_etoile = KARMAN * np.hypot(c["u"], c["v"]) / math.log(z / Z0_SOL)   # profil logarithmique, atmosphère neutre
    u_p95 = np.percentile(u_etoile.reshape(-1, *u_etoile.shape[2:]), 95, axis=0)
    glace = ((c["co2ice"] > SEUIL_GLACE) | (c["h2oice"] > SEUIL_GLACE)).mean(axis=(0, 1))
    grille = lambda x: sur_cellules(x, lat_m, lon_m, lat_c, lon_c)
    u_p95_c, rho_c = grille(u_p95), grille(c["rho"].mean(axis=(0, 1)))
    sol_nu = grille(1.0 - glace)
    del c, u_etoile

    # --- Montabone : opacité de la poussière par sol
    poussiere = tempetes = np.full(len(cellules), np.nan)
    m = montabone(args.annees_mars, args.seuil_tempete)
    if m is not None:
        poussiere = sur_cellules(m["cdod_tot"], m["lat"], m["lon"], lat_c, lon_c)
        tempetes = sur_cellules(m["tempetes_freq"], m["lat"], m["lon"], lat_c, lon_c)

    # --- MGD3 : emprise de la livraison dont vient chaque fichier
    dunes = dunes_mars(args, cellules, lat_c)

    ecrire("mars", res, cellules,
           {"u_etoile_p95": u_p95_c, "u_etoile_seuil": seuil_saltation("mars", rho_c), "densite_air": rho_c,
            "part_dunes": dunes, "part_sol_nu": sol_nu, "poussiere_opacite": poussiere, "tempetes_freq": tempetes})


def dunes_mars(args, cellules, lat_c) -> np.ndarray:
    def emprise_mgd3(gdf):                         # livraison MGD3 d'où vient le fichier
        centre = float(np.median(gdf.geometry.representative_point().y))
        return (60.0, 90.0) if centre > 60 else (-90.0, -60.0) if centre < -60 else (-65.0, 65.0)
    if not fichiers_dunes(args.mgd3):
        print(f"  dunes : aucun fichier dans {args.mgd3}, part_dunes laissée vide")
    return part_dunes(fichiers_dunes(args.mgd3), cellules, lat_c, args.resolution, emprise_mgd3)


def maj_dunes(args, corps: str) -> None:
    """Recalcule part_dunes (et couverture) dans un résultat déjà écrit, sans rien retélécharger."""
    print(f"\n=== {corps} : dunes seulement")
    chemin = SORTIE / f"{MODULE}_{corps}_h3_{args.resolution}.parquet"
    if not chemin.is_file():
        print(f"  {court(chemin, RACINE)} absent : lancer d'abord le calcul complet de ce corps")
        return
    t = pd.read_parquet(chemin)
    cellules = t["h3"].to_numpy()
    lat_c = np.array([h3.cell_to_latlng(c)[0] for c in cellules])
    t["part_dunes"] = (dunes_terre if corps == "earth" else dunes_mars)(args, cellules, lat_c)
    sauver(corps, args.resolution, t)


def montabone(annees: list[int], seuil_visible: float) -> dict | None:
    """Par point de grille, sur les années demandées : opacité moyenne de la colonne totale
    (cdodtot, la poussière réellement au-dessus du sol) et part des sols de tempête, jugée sur
    l'opacité ramenée à 610 Pa (cdod610, indépendante de l'altitude). Absorption à 9,3 µm."""
    import xarray as xr
    seuil = seuil_visible / VISIBLE_PAR_CDOD
    cumul, lat, lon, lues = None, None, None, []
    for my in annees:
        f = fichier_montabone(my)
        if f is None:
            continue
        with xr.open_dataset(f, decode_times=False) as ds:
            if not {"cdod610", "cdodtot"} <= set(ds.data_vars):
                print(f"  {f.name} : cdod610 ou cdodtot absent (variables : {list(ds.data_vars)}), ignoré")
                continue
            dim_t = "Time" if "Time" in ds.dims else "time"
            lire = lambda v: ds[v].transpose(dim_t, "latitude", "longitude").values.astype(np.float32)
            norm, tot = lire("cdod610"), lire("cdodtot")
            if lat is None:
                lat, lon = ds["latitude"].values.astype(float), ds["longitude"].values.astype(float)
        for x in (norm, tot):
            x[(x < 0) | (x > 50) | ~np.isfinite(x)] = np.nan            # sols manquants ou valeurs de remplissage
        c = {"somme_tot": np.nansum(tot, axis=0), "n_tot": np.isfinite(tot).sum(axis=0),
             "tempetes": (norm >= seuil).sum(axis=0), "n_norm": np.isfinite(norm).sum(axis=0)}
        cumul = c if cumul is None else {k: cumul[k] + c[k] for k in c}
        lues.append(my)
    if not lues:
        print("  Montabone : aucune année lue, poussiere_* et tempetes_* laissées vides (voir le README)")
        return None
    print(f"  Montabone : années martiennes {lues[0]} à {lues[-1]} ({len(lues)} ans), grille {len(lat)} × {len(lon)}")
    with np.errstate(invalid="ignore", divide="ignore"):
        return {"cdod_tot": np.where(cumul["n_tot"] > 0, cumul["somme_tot"] / cumul["n_tot"], np.nan),
                "tempetes_freq": np.where(cumul["n_norm"] > 0, cumul["tempetes"] / cumul["n_norm"], np.nan),
                "lat": lat, "lon": lon}


def fichier_montabone(my: int) -> Path | None:
    for dossier in (ENTREES / "montabone", CACHE / "montabone"):
        trouves = sorted(dossier.glob(f"dustscenario_MY{my}_*.nc")) if dossier.is_dir() else []
        if trouves:
            return trouves[-1]
    if my not in VERSIONS_MONTABONE:
        return None
    url = URL_MONTABONE.format(my=my, v=VERSIONS_MONTABONE[my])
    cible = CACHE / "montabone" / Path(url).name
    cible.parent.mkdir(parents=True, exist_ok=True)
    partiel = cible.with_suffix(".part")
    try:
        urllib.request.urlretrieve(url, partiel)
        partiel.replace(cible)
        print(f"  Montabone MY{my} téléchargé ({cible.stat().st_size / 1e6:.0f} Mo)")
        return cible
    except OSError as e:
        partiel.unlink(missing_ok=True)
        print(f"  Montabone MY{my} : téléchargement impossible ({e})")
        return None


def main() -> int:
    args = options()
    t0 = time.time()
    for corps in ("mars", "earth"):
        if corps in args.corps:
            maj_dunes(args, corps) if args.dunes_seulement else (mars if corps == "mars" else terre)(args)
    print(f"\nTerminé en {(time.time() - t0) / 60:.1f} min.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
