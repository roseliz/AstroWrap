"""\"Astrobiology, habitability, caves and subsurface\" module: preprocessing for Earth, Mars, and the Moon.

    python modules_pretraitement/astrobiology_habitability_caves/scripts/pretraitement.py                       # all three bodies
    python modules_pretraitement/astrobiology_habitability_caves/scripts/pretraitement.py --corps moon          # all options: --help

One row per H3 cell (resolution 5 by default; for Earth, land cells only), written to
pretreatment_data/astrobiology_habitability_caves/. All three bodies share the same columns: cataloged
caves and lava tubes, hot springs, mines, hydrated minerals. A column that is irrelevant
to a body is empty (unknown) or zero when the phenomenon does not exist (no mines on Mars).

Sources
  Earth  Mines: Maus et al. 2022 (polygons, v2). Caves and hot springs: OpenStreetMap (Overpass) and
         Wikidata; large caves and karst: WOKAM (BGR). Volcanoes: Smithsonian GVP. Lava tubes: Wikidata,
         OpenStreetMap names, optional team file.
  Mars   Mars Global Cave Candidate Catalog (MGC3, USGS, Cushing). OMEGA and CRISM hydrated mineral sites
         (Carter et al. 2013, ESA archive).
  Moon   LROC Lunar Pit Atlas (Wagner and Robinson); lava tube indices (Losarcos and Dombard 2026).
  This module is independent: Earth's volcanic context and hydrated minerals are in the litho_* and
  comp_* columns of the geology_mineralogy module, to be joined on (body, resolution, h3).
"""

from __future__ import annotations

import argparse
import csv
import http.client
import io
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import h3
import numpy as np
import pandas as pd

RACINE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RACINE / "scripts"))
from commun import court, reconstruire_duckdb  # noqa: E402
MODULE = "astrobiology_habitability_caves"
SORTIE = RACINE / "pretreatment_data" / MODULE
CACHE = RACINE / "cache" / MODULE
ENTREES = RACINE / "inputs" / MODULE

RAYON_KM = {"earth": 6371.0088, "mars": 3396.19, "moon": 1737.4}
PAS_TERRE = 0.05                          # degrés : grille des terres émergées de Natural Earth

# --- Colonnes (les mêmes sur les trois corps)
COLONNES = ["n_cavites", "n_tubes_lave", "n_indices_tubes", "n_sources_chaudes", "n_volcans", "part_mine", "part_karst",
            "n_sites_aqueux", "indice_aqueux", "source_inventaire", "couverture", "fiabilite"]
# Indicateurs dont le taux de présence donne `couverture` : seuls ceux que le corps peut avoir
INDICATEURS = {"earth": ["n_cavites", "n_sources_chaudes", "n_volcans", "part_mine", "part_karst"],
               "mars": ["n_cavites", "indice_aqueux"],
               "moon": ["n_cavites", "n_indices_tubes"]}
SOURCE_INVENTAIRE = {"earth": "OpenStreetMap + Wikidata + WOKAM (BGR)", "mars": "MGC3 (USGS)", "moon": "LROC Lunar Pit Atlas"}

# --- Liens
URL_NE = "https://naciscdn.org/naturalearth/10m/physical/{nom}.zip"
URL_MAUS = "https://download.pangaea.de/dataset/942325/files/global_mining_polygons_v2.gpkg"
URL_MGC3 = ("https://astrogeology.usgs.gov/ckan/dataset/c2960f77-ee20-4cc6-ac85-abbecc0fc7f6/resource/"
            "ccd54fb2-9a50-46bf-8971-80c241bb2f40/download/mars_cave_catalog.zip")
URL_HYDRATES = ("https://archives.esac.esa.int/psa/ftp/MARS-EXPRESS/OMEGA/MEX-M-OMEGA-5-DDR-GLOBAL-MAPS-V1.0/"
                "DATA/HYDROUS/HYDROUS_SITES_GEO_MAP.CSV")
URL_LROC = ("https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/EXTRAS/SHAPEFILE/LUNAR_PIT_LOCATIONS/"
            "LUNAR_PIT_LOCATIONS.CSV")
URL_WOKAM = "https://services.bgr.de/arcgis/rest/services/grundwasser/whymap_wokam/MapServer/"
WOKAM_CAVES, WOKAM_KARST = 1, 6            # couches : systèmes de grottes (points), roches karstifiables (polygones)
URL_GVP = ("https://webservices.volcano.si.edu/geoserver/GVP-VOTW/wfs?service=WFS&version=1.0.0&request=GetFeature"
           "&outputFormat=application/json&typeName=GVP-VOTW:")
COUCHES_GVP = ("Smithsonian_VOTW_Holocene_Volcanoes", "Smithsonian_VOTW_Pleistocene_Volcanoes")
URL_TUBES_LUNE = "https://zenodo.org/records/20516852/files/{nom}?download=1"       # Losarcos et Dombard 2026, CC BY 4.0
SERVEURS_OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
URL_WIKIDATA = "https://query.wikidata.org/sparql"
ENTETES = {"User-Agent": "Mozilla/5.0 (compatible; astrowrap)", "Accept": "*/*"}
# Overpass et Wikidata exigent un User-Agent qui décrit le programme (et refusent celui d'un navigateur)
ENTETES_API = {"User-Agent": "astrowrap/1.0 (research prototype)", "Accept": "*/*"}
# Classes Wikidata : grotte, tube de lave, source chaude
WD_GROTTE, WD_TUBE_LAVE, WD_SOURCE_CHAUDE = "Q35509", "Q27919", "Q177380"
REGEX_TUBE_LAVE = r"lava|lav[ao]s?\b|tubo|volc|basalt"        # noms d'entrées de grottes OpenStreetMap
PETITE_MINE_KM2 = 1.0                     # sous cette surface, une mine est comptée dans la cellule de son centre
DOUBLON_RES = 8                           # une entrée à moins d'une cellule de résolution 8 (~1 km) d'une autre = doublon
ENQUETE_MGC3_RES = 3                      # MGC3 : une cellule de résolution 3 (~3°) voisine d'un candidat a été étudiée
SITES = {
    "earth": {"Mammoth Cave": (37.19, -86.10), "Lava Beds (Californie)": (41.71, -121.51), "Ape Cave (St Helens)": (46.11, -122.21),
              "Yellowstone": (44.46, -110.83), "Rio Tinto (mines)": (37.72, -6.55), "Chuquicamata": (-22.30, -68.90),
              "Sahara (Ténéré)": (18.0, 10.0), "Groenland": (72.6, -38.5)},
    "mars": {"Arsia Mons": (-9.4, -120.1), "Pavonis Mons": (0.8, -112.9), "Nili Fossae": (21.0, 74.0),
             "Mawrth Vallis": (24.0, -19.0), "Meridiani": (-1.95, -5.53), "Jezero": (18.44, 77.45), "Gale": (-4.59, 137.44)},
    "moon": {"Marius Hills (fosse)": (14.09, -56.77), "Mare Tranquillitatis (fosse)": (8.335, 33.222), "Tycho": (-43.3, -11.4),
             "Apollo 11": (0.674, 23.473), "Shackleton": (-89.67, 129.78)},
}


# ------------------------------------------------------------------ outils
def options() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--corps", nargs="+", choices=("earth", "mars", "moon"), default=["earth", "mars", "moon"])
    p.add_argument("--resolution", type=int, default=5, help="résolution H3 (défaut : 5)")
    p.add_argument("--zone", type=float, nargs=4, metavar=("OUEST", "SUD", "EST", "NORD"),
                   help="limiter le calcul à une boîte lat/lon (essais)")
    g = p.add_argument_group("Terre")
    g.add_argument("--sans-osm", action="store_true", help="ne pas interroger OpenStreetMap (grottes et sources chaudes)")
    g.add_argument("--sans-wikidata", action="store_true", help="ne pas interroger Wikidata")
    g.add_argument("--tubes-lave", type=Path, default=ENTREES / "tubes_de_lave.csv",
                   help=f"fichier facultatif de l'équipe, colonnes nom,lat,lon (défaut : inputs/{MODULE}/tubes_de_lave.csv)")
    return p.parse_args()


def telecharger(url: str, cible: Path, tentatives: int = 6, silencieux: bool = False) -> bool:
    """Télécharge url dans cible (fichier .part renommé à la fin), en reprenant là où une coupure s'est arrêtée."""
    if cible.is_file() and cible.stat().st_size > 0:
        return True
    cible.parent.mkdir(parents=True, exist_ok=True)
    partiel = cible.with_name(cible.name + ".part")
    for essai in range(tentatives):
        debut = partiel.stat().st_size if partiel.exists() else 0
        entetes = dict(ENTETES)
        if debut:
            entetes["Range"] = f"bytes={debut}-"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=entetes), timeout=60) as r:
                reprise = debut > 0 and r.status == 206
                total = int(r.headers.get("Content-Range", "bytes 0-0/0").rsplit("/", 1)[-1] or 0) if reprise \
                    else int(r.headers.get("Content-Length", 0))
                with open(partiel, "ab" if reprise else "wb") as f:
                    shutil.copyfileobj(r, f, 1 << 20)
            if total and partiel.stat().st_size != total:
                continue
            partiel.replace(cible)
            if not silencieux:
                print(f"  {cible.name} téléchargé ({cible.stat().st_size / 1e6:.1f} Mo)", flush=True)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 416 and partiel.exists():
                partiel.replace(cible)
                return True
            if e.code in (401, 403, 404):
                partiel.unlink(missing_ok=True)
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


def compter(index: pd.Index, lat, lon, res: int, zone=None, poids=None) -> np.ndarray:
    """Nombre de points (ou somme de poids) par cellule de index ; les points hors des cellules sont ignorés."""
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    if zone:
        g = dans_zone(lat, lon, zone)
        lat, lon = lat[g], lon[g]
        poids = None if poids is None else np.asarray(poids)[g]
    pos = index.get_indexer(vers_cellules(lat, lon, res))
    ok = pos >= 0
    return np.bincount(pos[ok], weights=None if poids is None else np.asarray(poids, float)[ok], minlength=len(index))


def sans_doublons(lat, lon, deja_lat, deja_lon) -> np.ndarray:
    """Masque des points qui n'ont pas de voisin dans (deja_lat, deja_lon) à moins d'une cellule de résolution
    DOUBLON_RES (~1 km) : une grotte décrite par OpenStreetMap et par Wikidata ne compte qu'une fois."""
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    if len(deja_lat) == 0 or len(lat) == 0:
        return np.ones(len(lat), bool)
    cles = set()
    for c in vers_cellules(deja_lat, deja_lon, DOUBLON_RES):
        cles.update(h3.grid_disk(c, 1))
    return np.array([c not in cles for c in vers_cellules(lat, lon, DOUBLON_RES)])


def rang_nan(x):
    return np.asarray(x, dtype=np.float32)


def assembler(corps: str, res: int, cellules, v: dict) -> pd.DataFrame:
    n = len(cellules)
    nan = np.full(n, np.nan, dtype=np.float32)
    t = pd.DataFrame({"body": corps, "resolution": res, "h3": cellules})
    for c in ("n_cavites", "n_tubes_lave", "n_indices_tubes", "n_sources_chaudes", "n_volcans", "part_mine", "part_karst",
              "n_sites_aqueux", "indice_aqueux"):
        t[c] = np.asarray(v.get(c, nan), dtype=np.float32)
    t["source_inventaire"] = SOURCE_INVENTAIRE[corps]
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
    cols = [c for c in COLONNES if c not in ("source_inventaire", "fiabilite")]
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
    """Cellules de terre émergée : celles qui contiennent le centre d'au moins un pixel de 0,05° de terre de Natural Earth.
    Garde pour chaque pixel de terre la cellule où il tombe (agrégation du karst)."""
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
    t0 = time.time()
    cellules, inverse = np.unique(vers_cellules(lat, lon, args.resolution), return_inverse=True)
    print(f"  {len(cellules):,} cellules de terre émergée ({time.time() - t0:.0f} s)")
    return {"cellules": cellules, "lig": lig, "col": col, "inverse": inverse,
            "n_pix": np.bincount(inverse, minlength=len(cellules)).astype(float), "tr": tr, "forme": forme}


def wokam(couche: int, cible: Path, geometrie: bool):
    """Couche du service WOKAM (BGR) en GeoJSON, par pages de 2 000 éléments, mise en cache. Le certificat de BGR
    n'est reconnu que par la bibliothèque requests (urllib le refuse)."""
    if not (cible.is_file() and cible.stat().st_size > 0):
        import requests
        elements, debut = [], 0
        while True:
            params = {"where": "1=1", "outFields": "*", "f": "geojson", "outSR": 4326, "resultOffset": debut,
                      "resultRecordCount": 2000, "returnGeometry": "true" if geometrie else "false"}
            if geometrie:
                params["maxAllowableOffset"] = 0.02                           # ~2 km : assez pour une carte à 0,05°
            for essai in range(4):
                try:
                    r = requests.get(f"{URL_WOKAM}{couche}/query", params=params, headers=ENTETES_API, timeout=300)
                    r.raise_for_status()
                    page = r.json().get("features", [])
                    break
                except (requests.RequestException, ValueError) as e:
                    print(f"    WOKAM couche {couche} : {str(e)[:90]}")
                    time.sleep(10 * (essai + 1))
            else:
                return None
            elements += page
            if len(page) < 2000:
                break
            debut += 2000
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(json.dumps({"type": "FeatureCollection", "features": elements}), encoding="utf-8")
    return cible


def karst(args, T) -> np.ndarray:
    """Part de chaque cellule sur des roches karstifiables (WOKAM : carbonates, évaporites) : pixels de 0,05° de terre
    dont le centre tombe dans un polygone / pixels de terre de la cellule."""
    import geopandas as gpd
    from rasterio import features
    f = wokam(WOKAM_KARST, CACHE / "wokam_karst.geojson", True)
    if f is None:
        print("  WOKAM (karst) indisponible : part_karst laissée vide")
        return np.full(len(T["cellules"]), np.nan, np.float32)
    gdf = gpd.read_file(f)
    gdf = gdf[gdf.geometry.notna()]
    grille = features.rasterize(((g, 1) for g in gdf.geometry), out_shape=T["forme"], transform=T["tr"], fill=0, dtype="uint8")
    part = np.bincount(T["inverse"], weights=grille[T["lig"], T["col"]].astype(float), minlength=len(T["cellules"])) / T["n_pix"]
    print(f"  karst : {len(gdf):,} polygones WOKAM, {int((part > 0).sum()):,} cellules concernées")
    return np.clip(part, 0, 1).astype(np.float32)


def volcans():
    """Volcans de l'Holocène et du Pléistocène (Smithsonian GVP, service WFS public), sans doublon : DataFrame lat, lon."""
    pts = []
    for couche in COUCHES_GVP:
        cible = CACHE / f"gvp_{couche}.json"
        if not (cible.is_file() and cible.stat().st_size > 0):
            try:
                with urllib.request.urlopen(urllib.request.Request(URL_GVP + couche, headers=ENTETES_API), timeout=300) as r:
                    cible.parent.mkdir(parents=True, exist_ok=True)
                    cible.write_bytes(r.read())
            except (OSError, http.client.HTTPException) as e:
                print(f"  GVP ({couche}) indisponible : {str(e)[:90]}")
                return None
        for x in json.loads(cible.read_text(encoding="utf-8"))["features"]:
            g = x.get("geometry")
            if g and g.get("coordinates"):
                pts.append((x["properties"].get("Volcano_Number"), g["coordinates"][1], g["coordinates"][0]))
    return pd.DataFrame(pts, columns=["numero", "lat", "lon"]).drop_duplicates("numero")


def overpass_tsv(requete: str, cible: Path):
    """Requête Overpass en CSV (tabulations) mise en cache dans cible. Rend un DataFrame, ou None si les serveurs échouent."""
    if not (cible.is_file() and cible.stat().st_size > 0):
        corps = urllib.parse.urlencode({"data": requete}).encode()
        for essai in range(4):
            for serveur in SERVEURS_OVERPASS:
                try:
                    entetes = {**ENTETES_API, "Content-Type": "application/x-www-form-urlencoded"}
                    with urllib.request.urlopen(urllib.request.Request(serveur, data=corps, headers=entetes), timeout=900) as r:
                        donnees = r.read()
                    if donnees.startswith(b"<"):                          # page d'erreur XML/HTML
                        raise OSError(donnees[:120].decode("latin-1"))
                    cible.parent.mkdir(parents=True, exist_ok=True)
                    cible.write_bytes(donnees)
                    break
                except (OSError, http.client.HTTPException) as e:
                    print(f"    Overpass {serveur.split('/')[2]} : {str(e)[:90]}")
                    time.sleep(10 * (essai + 1))
            else:
                continue
            break
        else:
            return None
    return pd.read_csv(cible, sep="\t", dtype=str, quoting=csv.QUOTE_NONE, on_bad_lines="skip", keep_default_na=False)


def wikidata_points(classe: str, cible: Path):
    """Éléments Wikidata de la classe (et de ses sous-classes) avec des coordonnées : DataFrame nom, lat, lon."""
    if not (cible.is_file() and cible.stat().st_size > 0):
        requete = ("SELECT ?nom ?c WHERE { ?i wdt:P31/wdt:P279* wd:%s ; wdt:P625 ?c . "
                   "OPTIONAL { ?i rdfs:label ?nom FILTER(LANG(?nom) = 'en') } }" % classe)
        url = URL_WIKIDATA + "?format=json&query=" + urllib.parse.quote(requete)
        for essai in range(5):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={**ENTETES_API, "Accept": "application/sparql-results+json"}), timeout=300) as r:
                    lignes = json.load(r)["results"]["bindings"]
                break
            except urllib.error.HTTPError as e:
                print(f"    Wikidata {classe} : {e.code}" + (" (limite de débit, attente 70 s)" if e.code == 429 else ""))
                time.sleep(70 if e.code == 429 else 10 * (essai + 1))
            except (OSError, http.client.HTTPException) as e:
                print(f"    Wikidata {classe} : {str(e)[:80]}")
                time.sleep(10 * (essai + 1))
        else:
            return None
        pts = []
        for l in lignes:
            m = re.match(r"Point\(([-\d.eE+]+) ([-\d.eE+]+)\)", l["c"]["value"])
            if m:
                pts.append((l.get("nom", {}).get("value", ""), float(m.group(2)), float(m.group(1))))
        cible.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(pts, columns=["nom", "lat", "lon"]).drop_duplicates().to_csv(cible, index=False)
    return pd.read_csv(cible, keep_default_na=False)


def terre(args) -> None:
    print("\n=== Terre")
    res = args.resolution
    T = terres_emergees(args)
    cellules = T["cellules"]
    index = pd.Index(cellules)
    n = len(cellules)
    v, sources = {}, {}
    ni, nt, ns = np.zeros(n), np.zeros(n), np.zeros(n)

    # --- Grottes : OpenStreetMap, puis Wikidata sans les doublons, puis fichier de l'équipe
    cav_lat, cav_lon = np.array([]), np.array([])
    tube_lat, tube_lon = np.array([]), np.array([])
    source_chaude = [np.array([]), np.array([])]
    utilise = []
    if not args.sans_osm:
        d = overpass_tsv('[out:csv(::lat,::lon,"name";false;"\\t")][timeout:600];node["natural"="cave_entrance"];out;', CACHE / "osm_cave_entrance.tsv")
        if d is None:
            print("  OpenStreetMap indisponible : grottes OSM ignorées (relancer plus tard ; le résultat est mis en cache)")
        else:
            lat, lon = pd.to_numeric(d.iloc[:, 0], errors="coerce").to_numpy(), pd.to_numeric(d.iloc[:, 1], errors="coerce").to_numpy()
            ok = np.isfinite(lat) & np.isfinite(lon)
            cav_lat, cav_lon = lat[ok], lon[ok]
            noms = d.iloc[:, 2].astype(str).to_numpy()[ok]
            lave = pd.Series(noms).str.contains(REGEX_TUBE_LAVE, case=False, regex=True).to_numpy()
            tube_lat, tube_lon = cav_lat[lave], cav_lon[lave]
            print(f"  OpenStreetMap : {len(cav_lat):,} entrées de grottes, dont {int(lave.sum())} dont le nom évoque la lave")
            utilise.append("OpenStreetMap (natural=cave_entrance)")
        d = overpass_tsv('[out:csv(::lat,::lon;false;"\\t")][timeout:600];nwr["natural"="hot_spring"];out center;', CACHE / "osm_hot_spring.tsv")
        if d is not None:
            lat, lon = pd.to_numeric(d.iloc[:, 0], errors="coerce").to_numpy(), pd.to_numeric(d.iloc[:, 1], errors="coerce").to_numpy()
            ok = np.isfinite(lat) & np.isfinite(lon)
            source_chaude = [lat[ok], lon[ok]]
            print(f"  OpenStreetMap : {int(ok.sum()):,} sources chaudes")
    if not args.sans_wikidata:
        for classe, etiquette in ((WD_GROTTE, "grottes"), (WD_TUBE_LAVE, "tubes de lave"), (WD_SOURCE_CHAUDE, "sources chaudes")):
            d = wikidata_points(classe, CACHE / f"wikidata_{classe}.csv")
            if d is None:
                print(f"  Wikidata ({etiquette}) indisponible : ignoré")
                continue
            if classe == WD_SOURCE_CHAUDE:
                gardes = sans_doublons(d["lat"], d["lon"], *source_chaude)
                source_chaude = [np.concatenate([source_chaude[0], d["lat"].to_numpy()[gardes]]), np.concatenate([source_chaude[1], d["lon"].to_numpy()[gardes]])]
            else:
                gardes = sans_doublons(d["lat"], d["lon"], cav_lat, cav_lon)
                cav_lat = np.concatenate([cav_lat, d["lat"].to_numpy()[gardes]])
                cav_lon = np.concatenate([cav_lon, d["lon"].to_numpy()[gardes]])
                if classe == WD_TUBE_LAVE:
                    tube_lat = np.concatenate([tube_lat, d["lat"].to_numpy()])
                    tube_lon = np.concatenate([tube_lon, d["lon"].to_numpy()])
            print(f"  Wikidata ({etiquette}) : {len(d):,} éléments, {int(gardes.sum()):,} nouveaux après les doublons")
        utilise.append("Wikidata (grottes, tubes de lave, sources chaudes)")
    f = wokam(WOKAM_CAVES, CACHE / "wokam_caves.geojson", False)
    if f is not None:
        pts = [x["properties"] for x in json.loads(f.read_text(encoding="utf-8"))["features"]]
        d = pd.DataFrame(pts).dropna(subset=["x_wgs84", "y_wgs84"])
        gardes = sans_doublons(d["y_wgs84"], d["x_wgs84"], cav_lat, cav_lon)
        cav_lat = np.concatenate([cav_lat, d["y_wgs84"].to_numpy(float)[gardes]])
        cav_lon = np.concatenate([cav_lon, d["x_wgs84"].to_numpy(float)[gardes]])
        print(f"  WOKAM (systèmes de grottes) : {len(d)} grottes, {int(gardes.sum())} nouvelles après les doublons")
        utilise.append("WOKAM (BGR, systèmes de grottes)")
    else:
        print("  WOKAM (grottes) indisponible : ignoré")
    if args.tubes_lave.is_file():
        d = pd.read_csv(args.tubes_lave, comment="#", skipinitialspace=True)
        d = d.dropna(subset=["lat", "lon"])
        gardes = sans_doublons(d["lat"], d["lon"], cav_lat, cav_lon)
        cav_lat, cav_lon = np.concatenate([cav_lat, d["lat"].to_numpy()[gardes]]), np.concatenate([cav_lon, d["lon"].to_numpy()[gardes]])
        tube_lat, tube_lon = np.concatenate([tube_lat, d["lat"].to_numpy()]), np.concatenate([tube_lon, d["lon"].to_numpy()])
        print(f"  tubes de lave de l'équipe : {len(d)} lignes ({court(args.tubes_lave, RACINE)})")
        utilise.append("fichier tubes_de_lave.csv de l'équipe")
    ni = compter(index, cav_lat, cav_lon, res, args.zone)
    # un même tube peut avoir plusieurs enregistrements : un par cellule de résolution 8
    if len(tube_lat):
        uniques = pd.DataFrame({"c": vers_cellules(tube_lat, tube_lon, DOUBLON_RES), "lat": tube_lat, "lon": tube_lon}).drop_duplicates("c")
        nt = compter(index, uniques["lat"], uniques["lon"], res, args.zone)
    nt = np.minimum(nt, ni)                                                # un tube est aussi une cavité
    ns = compter(index, source_chaude[0], source_chaude[1], res, args.zone)
    v["n_cavites"], v["n_tubes_lave"], v["n_sources_chaudes"] = ni, nt, ns
    sources["cavites"] = " ; ".join(utilise) if utilise else "aucune (--sans-osm et --sans-wikidata)"
    sources["sources_chaudes"] = "OpenStreetMap (natural=hot_spring) et Wikidata (hot spring)"

    # --- Mines : Maus et al. 2022
    v["part_mine"], sources["mines"] = mines(args, cellules, index), "Maus et al. 2022, Global-scale mining polygons v2 (PANGAEA 942325, CC BY-SA 4.0)"
    # --- Karst (WOKAM) et volcans (Smithsonian GVP)
    v["part_karst"] = karst(args, T)
    sources["karst"] = "WHYMAP WOKAM (BGR Berlin, IAH, KIT, UNESCO 2017) : roches karstifiables, 2 805 polygones"
    d = volcans()
    if d is not None:
        v["n_volcans"] = compter(index, d["lat"], d["lon"], res, args.zone)
        print(f"  volcans : {len(d):,} (Holocène et Pléistocène), {int((v['n_volcans'] > 0).sum()):,} cellules concernées")
        sources["volcans"] = "Smithsonian Global Volcanism Program, Volcanoes of the World (Holocène et Pléistocène)"
    ecrire("earth", res, assembler("earth", res, cellules, v), sources)


def mines(args, cellules, index) -> np.ndarray:
    """Part de chaque cellule couverte de mines : surface des polygones de Maus et al. / surface de la cellule. Une mine
    de moins de PETITE_MINE_KM2 est comptée dans la cellule de son centre ; les autres par sous-cellules H3 (res + 3)."""
    import geopandas as gpd
    f = CACHE / "maus" / "global_mining_polygons_v2.gpkg"
    if not telecharger(URL_MAUS, f):
        print("  mines de Maus et al. indisponibles : part_mine laissée vide")
        return np.full(len(cellules), np.nan, np.float32)
    gdf = gpd.read_file(f)
    gdf = gdf[gdf.geometry.notna() & gdf.geom_type.isin(["Polygon", "MultiPolygon"])]
    res = args.resolution
    pts = gdf.geometry.representative_point()
    if args.zone:
        g = np.asarray(dans_zone(pts.y.to_numpy(), pts.x.to_numpy(), args.zone))
        gdf, pts = gdf[g], pts[g]
    petits = gdf["AREA"].to_numpy() < PETITE_MINE_KM2
    km2 = np.zeros(len(cellules))
    pos = index.get_indexer(vers_cellules(pts.y.to_numpy()[petits], pts.x.to_numpy()[petits], res))
    ok = pos >= 0
    np.add.at(km2, pos[ok], gdf["AREA"].to_numpy()[petits][ok])
    aire_fine = h3.average_hexagon_area(res + 3, unit="km^2")
    fines = []
    for geom in gdf.geometry[~petits]:
        fines.extend(h3.cell_to_parent(c, res) for c in h3.geo_to_cells(geom, res + 3))
    if fines:
        comptes = pd.Series(fines).value_counts()
        pos = index.get_indexer(comptes.index)
        ok = pos >= 0
        np.add.at(km2, pos[ok], comptes.to_numpy()[ok] * aire_fine)
    aire = np.array([h3.cell_area(c, unit="km^2") for c in cellules])
    print(f"  mines : {len(gdf):,} polygones, {gdf['AREA'].sum():,.0f} km², {int((km2 > 0).sum()):,} cellules concernées")
    return np.clip(km2 / aire, 0, 1).astype(np.float32)


# ------------------------------------------------------------------ Mars
def mars(args) -> None:
    print("\n=== Mars")
    res = args.resolution
    cellules, lat_c, lon_c = cellules_globales(res, args.zone)
    index = pd.Index(cellules)
    n = len(cellules)
    print(f"  {n:,} cellules H3 de résolution {res}")
    v, sources = {}, {}
    f = CACHE / "mgc3" / "mars_cave_catalog.zip"
    if telecharger(URL_MGC3, f):
        with zipfile.ZipFile(f) as z:
            donnees = z.read("data/Mars_Cave_Catalog.csv")
        # l'en-tête du fichier est dans un autre ordre que les colonnes : étiquette, longitude E, latitude, type, priorité
        d = pd.read_csv(io.BytesIO(donnees), header=0, names=["etiquette", "lon", "lat", "type", "priorite", "diametre", "profondeur", "commentaire"],
                        dtype={"etiquette": str, "type": str}, usecols=range(8))
        d["lat"], d["lon"] = pd.to_numeric(d["lat"], errors="coerce"), pd.to_numeric(d["lon"], errors="coerce")
        d = d.dropna(subset=["lat", "lon"])
        d["lon"] = (d["lon"] + 180) % 360 - 180
        cav = compter(index, d["lat"], d["lon"], res, args.zone)
        tubes = compter(index, d.loc[d["type"] == "sky", "lat"], d.loc[d["type"] == "sky", "lon"], res, args.zone)
        # MGC3 n'a cherché que dans 11 provinces volcaniques : hors d'une cellule de résolution 3 voisine d'un candidat, inconnu
        etudie = set()
        for c in vers_cellules(d["lat"], d["lon"], ENQUETE_MGC3_RES):
            etudie.update(h3.grid_disk(c, 1))
        parent = np.array([h3.cell_to_parent(c, ENQUETE_MGC3_RES) for c in cellules])
        enquete = np.array([p in etudie for p in parent])
        v["n_cavites"] = np.where(enquete, cav, np.nan)
        v["n_tubes_lave"] = np.where(enquete, tubes, np.nan)
        print(f"  MGC3 : {len(d):,} candidats, {int((d['type'] == 'sky').sum())} ouvertures de tubes de lave, {int(enquete.sum()):,} cellules étudiées")
        sources["cavites"] = "Mars Global Cave Candidate Catalog v1 (Cushing, USGS Astrogeology, 2017) : 1 062 candidats ; tubes de lave = type « sky »"
    else:
        print("  MGC3 indisponible : cavités laissées vides")
    f = CACHE / "omega_hydrous" / "HYDROUS_SITES_GEO_MAP.CSV"
    if telecharger(URL_HYDRATES, f):
        d = pd.read_csv(f, header=None, names=["lon", "lat", "omega", "crism"], usecols=range(4))
        sites = compter(index, d["lat"], d["lon"], res, args.zone)
        v["n_sites_aqueux"] = sites
        v["indice_aqueux"] = (sites > 0).astype(np.float32)
        print(f"  minéraux hydratés : {len(d):,} sites de Carter et al., {int((sites > 0).sum()):,} cellules concernées")
        sources["minéraux_hydratés"] = "Carter et al. 2013 (JGR) : sites de minéraux hydratés vus par OMEGA et CRISM, archive MEX-M-OMEGA-5-DDR-GLOBAL-MAPS-V1.0 (ESA PSA)"
    else:
        print("  sites hydratés indisponibles : minéraux hydratés laissés vides")
    v["part_mine"] = np.zeros(n, np.float32)                               # pas d'exploitation minière
    ecrire("mars", res, assembler("mars", res, cellules, v), sources)


# ------------------------------------------------------------------ Lune
def indices_tubes_lune(index, res: int, zone) -> np.ndarray:
    """Indices indirects de tubes de lave sous la surface de la Lune (Losarcos et Dombard 2026, d'après Kaku, Carrer, Chappaz
    et Zhu) : points de radar et de géophysique, et anomalies de gravité (polygones, comptés une fois, à leur centre).
    Les rainures sinueuses et les chaînes d'effondrement du même jeu (lignes) ne sont pas comptées."""
    import geopandas as gpd
    pts = []
    for nom, forme in (("Points.zip", "points"), ("Polygons.zip", "polygones")):
        f = CACHE / "tubes_lune" / nom
        if not telecharger(URL_TUBES_LUNE.format(nom=nom), f):
            print(f"  {nom} indisponible : indices de tubes lunaires incomplets")
            continue
        gdf = gpd.read_file(f"zip://{f.as_posix()}")
        gdf = gdf[gdf.geometry.notna()]
        c = gdf.geometry.representative_point()
        pts += list(zip(c.y.to_numpy(), c.x.to_numpy()))
        print(f"  {forme} d'indices de tubes : {len(gdf)}")
    if not pts:
        return np.full(len(index), np.nan, np.float32)
    lat, lon = zip(*pts)
    return compter(index, lat, lon, res, zone).astype(np.float32)


def lune(args) -> None:
    print("\n=== Lune")
    res = args.resolution
    cellules, lat_c, lon_c = cellules_globales(res, args.zone)
    index = pd.Index(cellules)
    n = len(cellules)
    print(f"  {n:,} cellules H3 de résolution {res}")
    v, sources = {}, {}
    f = CACHE / "lroc" / "LUNAR_PIT_LOCATIONS.CSV"
    if telecharger(URL_LROC, f):
        d = pd.read_csv(f, encoding="latin-1")                              # le fichier de LROC n'est pas en UTF-8
        d = d.dropna(subset=["Latitude", "Longitude_180"])
        v["n_cavites"] = compter(index, d["Latitude"], d["Longitude_180"], res, args.zone)
        mare = d["Terrain"].astype(str).str.lower().eq("mare")
        v["n_tubes_lave"] = compter(index, d.loc[mare, "Latitude"], d.loc[mare, "Longitude_180"], res, args.zone)
        print(f"  LROC : {len(d)} fosses, dont {int(mare.sum())} en mer basaltique (ouvertures possibles de tubes de lave)")
        sources["cavites"] = "LROC Lunar Pit Atlas (Wagner et Robinson 2021) : fosses ; tubes de lave = fosses en mer basaltique"
    else:
        print("  LROC indisponible : cavités laissées vides")
    v["n_indices_tubes"] = indices_tubes_lune(index, res, args.zone)
    sources["indices_tubes"] = "Losarcos et Dombard 2026 (Zenodo 20516852, CC BY 4.0) : indices radar et de gravité de tubes de lave"
    v["part_karst"] = np.zeros(n, np.float32)                              # pas de roche soluble
    v["n_sources_chaudes"] = np.zeros(n, np.float32)                       # pas d'eau liquide ni de volcanisme actif
    v["part_mine"] = np.zeros(n, np.float32)
    v["n_sites_aqueux"] = np.zeros(n, np.float32)                          # pas d'altération aqueuse connue
    v["indice_aqueux"] = np.zeros(n, np.float32)
    ecrire("moon", res, assembler("moon", res, cellules, v), sources)


def main() -> int:
    args = options()
    t0 = time.time()
    for corps, fonction in (("moon", lune), ("mars", mars), ("earth", terre)):
        if corps in args.corps:
            fonction(args)
    print(f"\nTerminé en {(time.time() - t0) / 60:.1f} min.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
