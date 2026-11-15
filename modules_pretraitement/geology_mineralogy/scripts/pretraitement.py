"""Geology, mineralogy and surface materials module: preprocessing of Earth, Mars and the Moon.

    python modules_pretraitement/geology_mineralogy/scripts/pretraitement.py                      # all three bodies
    python modules_pretraitement/geology_mineralogy/scripts/pretraitement.py --bodies moon mars   # options: --help

One row per H3 cell (resolution 5 by default; on Earth, land cells only), written to
pretreatment_data/geology_mineralogy/. Two vectors, compared separately:

  comp_<family>   composition in 12 mineral families, iron oxides apart (sums to 1 over the families the
                  body's instrument can see; the others are NaN, meaning "not observed", not "absent")
  litho_<class>   fraction of the cell in each rock class shared by the three bodies (sums to 1)

Sources
  Earth  EMIT L2B MIN v001 (NASA/JPL, over the zones of emit.EMIT_ZONES) and EMIT L3 ASA elsewhere,
         GLiM (global lithological map), MODIS MCD12C1 (land, vegetation, urban areas)
  Mars   OMEGA (Mars Express) global maps of olivine, pyroxene and ferric oxides (Ody et al. 2012),
         USGS SIM 3292 global geologic map (Tanaka et al. 2014)
  Moon   olivine, plagioclase and pyroxene abundances (Lucey et al. 2021, Kaguya MI + Diviner),
         USGS Unified Geologic Map of the Moon (2020)
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.request
import warnings
from pathlib import Path

import h3
import numpy as np
import pandas as pd

from emit import EMIT_ZONES, granule_counts, merge_counts
from families import ALL_FAMILIES, MINERAL_FAMILIES
from lithology import ROCK_CLASSES, class_ranks
from utils import check_free_space, rebuild_duckdb, short_path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                            # repository root
MODULE = "geology_mineralogy"
OUTPUT_DIR = ROOT / "pretreatment_data" / MODULE
CACHE_DIR = ROOT / "cache" / MODULE
INPUT_DIR = ROOT / "inputs" / MODULE

# Some servers (astrogeology.usgs.gov) reject the default "Python-urllib" agent with HTTP 403
_opener = urllib.request.build_opener()
_opener.addheaders = [("User-Agent", "analogues-pipeline/1.0 (NASA Space Apps Challenge 2026)")]
urllib.request.install_opener(_opener)
# The lunar GeoTIFFs from Zenodo are not georeferenced: their latitude/longitude files are read instead
warnings.filterwarnings("ignore", message="Dataset has no geotransform")

# Iron oxides are kept out of the composition: on Earth, EMIT gives a second mineral per pixel (group 2,
# near 1 um) that is almost always an iron oxide, which put them at ~50 % everywhere. They have their own
# column, part_oxyde_fer (fraction of the measured pixels where an iron oxide is detected).
COMPOSITION_FAMILIES = [f for f in MINERAL_FAMILIES if f != "oxyde_fer"]
# Families that each body's instrument can see; the other comp_ columns are NaN
VISIBLE_FAMILIES = {"earth": COMPOSITION_FAMILIES,
                    "mars": ["pyroxene", "olivine"],
                    "moon": ["pyroxene", "olivine", "feldspath"]}

# --- Mars: OMEGA global maps (ESA PSA), 40 pixels per degree
OMEGA_URL = "https://archives.esac.esa.int/psa/ftp/MARS-EXPRESS/OMEGA/MEX-M-OMEGA-5-DDR-GLOBAL-MAPS-V1.0/DATA/{folder}/{name}"
OMEGA_MAPS = {"olivine": ("OLIVINE", "OLIVINE_OSP1_EQU_MAP"), "pyroxene": ("PYROXENE", "PYROXENE_BD2000_EQU_MAP"),
              "ferric": ("FERRIC", "FERRIC_BD530_EQU_MAP")}
# The olivine and pyroxene maps only contain the pixels above the detection thresholds of Ody et al.
# (2012, table 3: OSP1 >= 1.04; 2 um band depth >= 1 %), and are missing elsewhere. The Fe3+ parameter
# (BD530) is positive on every observed pixel: it tells where OMEGA measured, and a ferric oxide is only
# counted on strongly oxidized surfaces (BD530 >= 0.20; 0.20 to 0.23 in bright regions).
OMEGA_THRESHOLDS = {"olivine": 1.04, "pyroxene": 0.01, "ferric": 0.20}
# --- Mars: SIM 3292 geologic map (USGS), as GeoJSON
MARS_MAP_URLS = [
    "https://astrogeology.usgs.gov/pygeoapi/collections/mars/sim3292_global_geologic_map/units/items?f=json&limit={n}&offset={start}",
    "https://services.arcgis.com/nzS0F0zdNLvs7nc8/ArcGIS/rest/services/Mars_Geology_feature_layer/FeatureServer/0/query"
    "?where=1%3D1&outFields=Unit,UnitDesc&f=geojson&resultRecordCount={n}&resultOffset={start}",
]
# --- Moon: mineral abundances (Zenodo 4558194, CC BY 4.0), 32 pixels per degree, +/-70 deg
MOON_URL = "https://zenodo.org/records/4558194/files/diviner_MI_{name}.tiff?download=1"
MOON_MINERALS = {"olivine": "olivine", "plagioclase": "feldspath", "pyroxene": "pyroxene"}
# --- Earth: EMIT L3 ASA, mean abundances of 10 minerals on a 0.5 deg grid (arid regions, +/-52 deg)
EMIT_L3_MINERALS = {"calcite": "carbonate", "dolomite": "carbonate", "chlorite": "argile_fe_mg",
                    "vermiculite": "argile_fe_mg", "goethite": "oxyde_fer", "hematite": "oxyde_fer",
                    "gypsum": "sulfate", "illite": "mica", "muscovite": "mica", "kaolinite": "argile_al",
                    "montmorillonite": "argile_al"}

EMIT_PIXEL_M = 60.0
RADIUS_KM = {"earth": 6371.007, "mars": 3396.2, "moon": 1737.4}
MINERALOGY_SOURCE = {"earth": "EMIT L2B", "mars": "OMEGA", "moon": "Kaguya MI + Diviner"}

# Reference sites printed after each run, as a quick sanity check
SITES = {
    "earth": {"Atacama": (-24.5, -69.25), "Rio Tinto": (37.7, -6.55), "Death Valley": (36.46, -116.87),
              "Mauna Kea": (19.82, -155.47), "Pilbara": (-21.2, 119.5), "Montreal": (45.5, -73.57)},
    "mars": {"Jezero": (18.44, 77.45), "Nili Fossae": (22.0, 76.5), "Meridiani": (-1.95, -5.53),
             "Gale": (-4.59, 137.44), "Olympus Mons": (18.65, -133.8), "North polar cap": (87.0, 0.0)},
    "moon": {"Apollo 11 (mare)": (0.674, 23.473), "Apollo 16 (highlands)": (-8.973, 15.5),
             "Taurus-Littrow (pyroclastic)": (20.191, 30.772), "Tycho": (-43.31, -11.36),
             "Shackleton": (-89.67, 129.78)},
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bodies", nargs="+", choices=("earth", "mars", "moon"), default=["earth", "mars", "moon"],
                   help="bodies to process (default: all three)")
    p.add_argument("--resolution", type=int, default=5, help="H3 resolution (default: 5)")
    g = p.add_argument_group("Earth")
    g.add_argument("--year", type=int, default=2023, help="MCD12C1 year (default: 2023)")
    g.add_argument("--glim", type=Path, default=INPUT_DIR / "glim",
                   help=f"GLiM folder (default: inputs/{MODULE}/glim)")
    g.add_argument("--emit-max", type=int, default=12,
                   help="maximum EMIT granules per zone, least cloudy first (default: 12)")
    g.add_argument("--emit-step", type=int, default=1,
                   help="read one EMIT pixel in N along each direction (default: 1, all pixels)")
    g.add_argument("--no-emit", action="store_true", help="skip EMIT (lithology and masks only)")
    g.add_argument("--no-emit-l3", action="store_true", help="do not fill the cells outside the zones with EMIT L3")
    g = p.add_argument_group("Mars and Moon")
    g.add_argument("--mars-map", type=Path, default=INPUT_DIR / "carte_mars",
                   help=f"Mars geologic map, if the download fails (default: inputs/{MODULE}/carte_mars)")
    g.add_argument("--moon-map", type=Path, default=INPUT_DIR / "carte_lune",
                   help=f"Unified Geologic Map of the Moon (default: inputs/{MODULE}/carte_lune)")
    return p.parse_args()


# ------------------------------------------------------------------ helpers
def download(url: str, target: Path) -> bool:
    """Download `url` to `target` (through a .part file), unless it is already there."""
    if target.is_file() and target.stat().st_size > 0:
        return True
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    try:
        print(f"  downloading {target.name}...", flush=True)
        urllib.request.urlretrieve(url, partial)
        partial.replace(target)
        return True
    except OSError as e:
        partial.unlink(missing_ok=True)
        print(f"  {target.name}: download failed ({e})")
        return False


def global_cells(res: int):
    """Every H3 cell of resolution `res`, with the latitude and longitude of its center."""
    cells = np.array([c for r0 in h3.get_res0_cells() for c in h3.cell_to_children(r0, res)])
    centers = np.array([h3.cell_to_latlng(c) for c in cells])
    return cells, centers[:, 0], centers[:, 1]


def cell_sample_points(cells):
    """Center and 6 vertices (pulled 5 % toward the center) of each cell: 7 points to estimate the
    fraction of each class of a vector map. Returns lat, lon and the cell index of every point."""
    lat, lon, idx = [], [], []
    for i, c in enumerate(cells):
        clat, clon = h3.cell_to_latlng(c)
        lat.append(clat)
        lon.append(clon)
        idx.append(i)
        for vlat, vlon in h3.cell_to_boundary(c):
            dlon = (vlon - clon + 180) % 360 - 180
            lat.append(clat + 0.95 * (vlat - clat))
            lon.append(clon + 0.95 * dlon)
            idx.append(i)
    lon = (np.asarray(lon) + 180) % 360 - 180
    return np.asarray(lat), lon, np.asarray(idx)


def to_cells(lat, lon, res: int) -> np.ndarray:
    return np.array([h3.latlng_to_cell(float(a), float(b), res) for a, b in zip(lat, lon)])


def class_fractions(point_class: np.ndarray, cell_index: np.ndarray, n: int):
    """point_class: class rank at each point (-1 = unknown) -> per-cell class fractions (n, classes)
    and coverage (fraction of the points with a known class)."""
    known = point_class >= 0
    total = np.bincount(cell_index, minlength=n).astype(float)
    n_known = np.bincount(cell_index[known], minlength=n).astype(float)
    fractions = np.zeros((n, len(ROCK_CLASSES)), dtype=np.float32)
    for k in range(len(ROCK_CLASSES)):
        fractions[:, k] = np.bincount(cell_index[point_class == k], minlength=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        fractions = np.where(n_known[:, None] > 0, fractions / n_known[:, None], np.nan).astype(np.float32)
        coverage = np.where(total > 0, n_known / total, 0.0)
    return fractions, coverage


def rasterize_classes(gdf, column: str, step: float = 0.05):
    """Polygons in longitude/latitude -> global grid of class ranks (255 = none), and its transform."""
    from rasterio import features
    from rasterio.transform import from_origin
    transform = from_origin(-180, 90, step, step)
    shape = (int(round(180 / step)), int(round(360 / step)))
    g = gdf[gdf[column] >= 0]
    grid = features.rasterize(((geom, int(v)) for geom, v in zip(g.geometry, g[column])), out_shape=shape,
                              transform=transform, fill=255, dtype="uint8")
    return grid, transform


def sample_grid(grid: np.ndarray, transform, lat, lon) -> np.ndarray:
    """Class rank of `grid` at each point (-1 = none)."""
    row = np.clip(((transform.f - lat) / -transform.e).astype(np.int64), 0, grid.shape[0] - 1)
    col = np.clip(((lon - transform.c) / transform.a).astype(np.int64), 0, grid.shape[1] - 1)
    v = grid[row, col].astype(np.int16)
    v[v == 255] = -1
    return v


def map_lithology(gdf, body: str, cells) -> tuple[np.ndarray, np.ndarray]:
    """Rock class fractions and lithology coverage of each cell, from a geologic map in lon/lat."""
    ranks = class_ranks(body)
    field = unit_column(gdf, set(ranks))
    gdf["rank"] = gdf[field].astype(str).str.strip().map(ranks).fillna(-1).astype(int)
    unknown = sorted(set(gdf.loc[gdf["rank"] < 0, field].astype(str)))
    print(f"  map: {len(gdf):,} polygons, field '{field}'" + (f", unclassified units: {unknown}" if unknown else ""))
    grid, transform = rasterize_classes(gdf, "rank")
    plat, plon, idx = cell_sample_points(cells)
    return class_fractions(sample_grid(grid, transform, plat, plon), idx, len(cells))


def sum_blocks_per_cell(blocks: dict, lat_b: np.ndarray, lon_b: np.ndarray, cells, lat_c, lon_c, res: int) -> dict:
    """Add up values carried by a grid of blocks (lat_b x lon_b) into the H3 cells: each cell receives the
    blocks whose center falls inside it; if there are none, the block that contains its center."""
    n = len(cells)
    reference = blocks.get("n_pixels", next(iter(blocks.values())))
    used = np.nonzero(reference.ravel() > 0)[0]                          # blocks read (measured or not)
    il, jl = np.unravel_index(used, reference.shape)
    position = pd.Index(cells).get_indexer(to_cells(lat_b[il], lon_b[jl], res))
    keep = position >= 0
    out = {}
    for k, b in blocks.items():
        out[k] = np.bincount(position[keep], weights=b.ravel()[used][keep], minlength=n)
    empty = np.bincount(position[keep], minlength=n) == 0
    if empty.any():
        step_lat, step_lon = lat_b[1] - lat_b[0], lon_b[1] - lon_b[0]
        fi = (lat_c[empty] - lat_b[0]) / step_lat
        i = np.clip(np.rint(fi).astype(int), 0, len(lat_b) - 1)
        j = np.clip(np.rint((lon_c[empty] - lon_b[0]) / step_lon).astype(int), 0, len(lon_b) - 1)
        inside = (fi > -0.5) & (fi < len(lat_b) - 0.5)                     # outside the grid (Moon beyond +/-70 deg): nothing
        for k, b in blocks.items():
            out[k][empty] = np.where(inside, b[i, j], 0)
    return out


def mineralogy_coverage(d: dict, measured, km2_per_pixel, area_km2) -> np.ndarray:
    """Mars, Moon: measured pixels / pixels read in the cell's blocks (1 when everything is measured,
    whatever the block size). Earth (EMIT): area of the measured pixels / cell area."""
    with np.errstate(invalid="ignore", divide="ignore"):
        if "n_pixels" in d:
            c = np.where(d["n_pixels"] > 0, measured / np.maximum(d["n_pixels"], 1), 0)
        else:
            c = measured * km2_per_pixel / area_km2
    return np.clip(c, 0, 1).astype(np.float32)


def assemble(body: str, res: int, cells, counts: dict | None, abundances: dict | None, litho, litho_coverage,
             masks: dict | None, km2_per_pixel: float | None) -> pd.DataFrame:
    """Build the output table. counts: n_mesures, n_detecte, n_<family> (Earth, Mars);
    abundances: mean <family> abundance and n_mesures (Moon)."""
    n = len(cells)
    t = pd.DataFrame({"body": body, "resolution": res, "h3": cells})
    visible = VISIBLE_FAMILIES[body]
    nan = np.full(n, np.nan, dtype=np.float32)
    # h3 gives the area on the Earth sphere: rescale it to the body radius
    area_km2 = np.array([h3.cell_area(c, unit="km^2") for c in cells]) * (RADIUS_KM[body] / 6371.007) ** 2
    if body != "earth":                                                  # pixels in degrees: smaller toward the poles
        area_km2 = area_km2 / np.maximum(np.cos(np.radians([h3.cell_to_latlng(c)[0] for c in cells])), 1e-3)
    if counts is not None:
        measured = counts["n_mesures"].astype(float)
        total = sum(counts[f"n_{f}"] for f in visible).astype(float)
        with np.errstate(invalid="ignore", divide="ignore"):
            for f in COMPOSITION_FAMILIES:
                t[f"comp_{f}"] = np.where(total > 0, counts[f"n_{f}"] / total, np.nan).astype(np.float32) if f in visible else nan
            t["part_oxyde_fer"] = np.where(measured > 0, counts["n_oxyde_fer"] / measured, np.nan).astype(np.float32)
            t["taux_detection"] = np.where(measured > 0, counts["n_detecte"] / measured, np.nan).astype(np.float32)
        t["couverture_mineralogie"] = mineralogy_coverage(counts, measured, km2_per_pixel, area_km2)
        if masks is not None and "vegetation" in masks:
            # Earth: EMIT cannot see minerals under dense vegetation; only the rest of the cell counts
            v = masks.get("vegetation_dense", masks["vegetation"])
            t["couverture_mineralogie"] *= (1 - np.clip(v, 0, 1)).astype(np.float32)
        for k in ["n_mesures", "n_detecte", *[f"n_{f}" for f in MINERAL_FAMILIES]]:
            t[k] = np.asarray(counts.get(k, np.zeros(n)), dtype=np.float64)
    else:
        measured = abundances["n_mesures"].astype(float)
        total = sum(abundances[f] for f in visible)
        with np.errstate(invalid="ignore", divide="ignore"):
            for f in COMPOSITION_FAMILIES:
                t[f"comp_{f}"] = np.where(total > 0, abundances[f] / total, np.nan).astype(np.float32) if f in visible else nan
            t["part_oxyde_fer"] = nan                                   # no ferric oxide data for the Moon
            t["taux_detection"] = np.where(measured > 0, (total > 0).astype(float), np.nan).astype(np.float32)
        t["couverture_mineralogie"] = mineralogy_coverage(abundances, measured, km2_per_pixel, area_km2)
        t["n_mesures"] = measured                                         # abundances: no per-family counts
        t["n_detecte"] = np.where(total > 0, measured, 0.0)
        for f in MINERAL_FAMILIES:
            t[f"n_{f}"] = np.nan
    for k, c in enumerate(ROCK_CLASSES):
        t[f"litho_{c}"] = litho[:, k]
    t["couverture_lithologie"] = np.asarray(litho_coverage, dtype=np.float32)
    m = masks or {}
    t["part_vegetation"] = np.asarray(m.get("vegetation", np.zeros(n)), dtype=np.float32)
    t["part_artificiel"] = np.asarray(m.get("artificiel", np.zeros(n)), dtype=np.float32)
    t["source_mineralogie"] = pd.Series(np.where(measured > 0, MINERALOGY_SOURCE[body], None), dtype="object")
    t["couverture"] = (0.5 * t["couverture_mineralogie"] + 0.5 * t["couverture_lithologie"]).astype(np.float32)
    t["fiabilite"] = t["couverture"]                                       # provisional, same rule as the other modules
    return t


def write_outputs(body: str, res: int, t: pd.DataFrame, sources: dict) -> None:
    """Write the Parquet file, rebuild the body's DuckDB database and print the reference sites."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{MODULE}_{body}_h3_{res}.parquet"
    table = pa.Table.from_pandas(t, preserve_index=False)
    meta = {"module": MODULE, "body": body, "families": json.dumps(COMPOSITION_FAMILIES),
            "visible_families": json.dumps(VISIBLE_FAMILIES[body]), "classes": json.dumps(ROCK_CLASSES),
            "sources": json.dumps(sources, ensure_ascii=False)}
    table = table.replace_schema_metadata({**(table.schema.metadata or {}), **{k: v.encode() for k, v in meta.items()}})
    pq.write_table(table, path, compression="zstd")
    rebuild_duckdb(OUTPUT_DIR, body)
    print(f"{body}: {len(t):,} cells written to {short_path(path, ROOT)}")

    ti = t.set_index("h3")
    comp_columns = [f"comp_{f}" for f in VISIBLE_FAMILIES[body]]
    rows = []
    for site, (la, lo) in SITES[body].items():
        c = h3.latlng_to_cell(la, lo, res)
        if c not in ti.index:
            rows.append({"site": site, "main rock": "outside the cells"})
            continue
        r = ti.loc[c]
        litho = r[[f"litho_{k}" for k in ROCK_CLASSES]].astype(float)
        comp = r[comp_columns].astype(float)
        rows.append({"site": site,
                     "main rock": litho.idxmax()[6:] if litho.notna().any() else "-",
                     "fraction": round(float(litho.max()), 2) if litho.notna().any() else np.nan,
                     "main mineral": comp.idxmax()[5:] if comp.notna().any() else "-",
                     "comp": round(float(comp.max()), 2) if comp.notna().any() else np.nan,
                     "iron oxide": round(float(r["part_oxyde_fer"]), 2),
                     "source": r["source_mineralogie"] or "-",
                     "mineral coverage": round(float(r["couverture_mineralogie"]), 2)})
    with pd.option_context("display.width", 250, "display.max_columns", None):
        print(pd.DataFrame(rows).to_string(index=False))
        print(f"Cells with minerals: {int(t[comp_columns].notna().any(axis=1).sum()):,}, "
              f"with lithology: {int(t['couverture_lithologie'].gt(0).sum()):,}")
        print("Cells per mineralogy source:", t["source_mineralogie"].value_counts().to_dict())
        print("Mean rock class fractions:", t[[f"litho_{k}" for k in ROCK_CLASSES]].mean().round(3)
              .rename(lambda c: c[6:]).loc[lambda s: s > 0].to_dict())


# ------------------------------------------------------------------ Earth
def earthdata_login():
    import earthaccess
    if not earthaccess.login().authenticated:
        sys.exit("NASA Earthdata login failed: put your credentials in ~/.netrc, or set "
                 "EARTHDATA_USERNAME and EARTHDATA_PASSWORD")
    return earthaccess


def fetch(ea, item, folder: Path) -> Path | None:
    """Download an earthaccess granule or data URL and return the first file (None on failure)."""
    folder.mkdir(parents=True, exist_ok=True)
    for attempt in range(2):
        try:
            try:
                files = ea.download([item], local_path=str(folder), show_progress=False)
            except TypeError:                                              # older earthaccess versions
                files = ea.download([item], local_path=str(folder))
        except Exception as e:                                             # network error raised by earthaccess
            files = [e]
        # earthaccess may return the exception in the list instead of raising it (e.g. 502 Bad Gateway)
        if files and not isinstance(files[0], Exception) and Path(str(files[0])).is_file():
            return Path(str(files[0]))
        if attempt == 0:
            time.sleep(10)
    print(f"    {str(item).rsplit('/', 1)[-1]}: download failed ({files[0] if files else 'nothing received'}), skipped")
    return None


def process_earth(args: argparse.Namespace) -> None:
    print("\n=== Earth")
    res = args.resolution
    ea = earthdata_login()

    # --- MODIS MCD12C1: land, vegetation and urban areas (0.05 deg)
    from pyhdf.SD import SD, SDC
    g = ea.search_data(short_name="MCD12C1", version="061", temporal=(f"{args.year}-01-01", f"{args.year}-12-31")) \
        or ea.search_data(short_name="MCD12C1", version="061", temporal=(f"{args.year - 1}-01-01", f"{args.year - 1}-12-31"))
    if not g:
        sys.exit("MCD12C1 not found")
    check_free_space(CACHE_DIR, 2.5, "MCD12C1 (1.2 GB) and the EMIT granules")
    path = fetch(ea, g[0], CACHE_DIR / "mcd12c1")
    if path is None:
        sys.exit("MCD12C1: download failed")
    try:
        sd = SD(str(path), SDC.READ)
    except Exception as e:                                                 # truncated file (full disk, network)
        path.unlink(missing_ok=True)
        sys.exit(f"MCD12C1 unreadable ({e}): incomplete file deleted; check the free disk space and run again")
    s = sd.select("Land_Cover_Type_1_Percent")
    axis = list(s.info()[2]).index(17)
    pct = np.moveaxis(s[:], axis, 2)                                       # (lat, lon, 17 IGBP classes), in %
    sd.end()
    path.unlink(missing_ok=True)
    water = pct[..., 0].astype(np.float32)
    step = 180.0 / water.shape[0]
    row, col = np.nonzero(water < 50)
    pix_lat, pix_lon = 90 - step * (row + 0.5), -180 + step * (col + 0.5)
    land_pct = np.maximum(100 - water[row, col], 1)
    # IGBP classes 1-12 and 14: vegetation; 13: urban
    vegetation = pct[row, col][:, [*range(1, 13), 14]].sum(axis=1) / land_pct
    # Dense vegetation (forests, closed shrublands, woody savannas, wetlands, croplands): EMIT cannot see
    # the ground. Open shrublands, savannas and grasslands (7, 9, 10) leave the ground visible (Pilbara,
    # Atacama): they do not reduce the mineral coverage.
    dense = pct[row, col][:, [1, 2, 3, 4, 5, 6, 8, 11, 12, 14]].sum(axis=1) / land_pct
    urban = pct[row, col, 13] / land_pct
    del pct, water
    t0 = time.time()
    cells, inverse = np.unique(to_cells(pix_lat, pix_lon, res), return_inverse=True)
    n = len(cells)
    nb = np.bincount(inverse, minlength=n)
    masks = {"vegetation": np.bincount(inverse, weights=vegetation, minlength=n) / nb,
             "vegetation_dense": np.bincount(inverse, weights=dense, minlength=n) / nb,
             "artificiel": np.bincount(inverse, weights=urban, minlength=n) / nb}
    print(f"  MCD12C1: {n:,} land cells ({time.time() - t0:.0f} s)")

    # --- GLiM: rock class at each land pixel
    pixel_class = glim_classes_at(args.glim, pix_lat, pix_lon)
    if pixel_class is not None:
        litho, litho_coverage = class_fractions(pixel_class, inverse, n)
    else:
        litho, litho_coverage = np.full((n, len(ROCK_CLASSES)), np.nan, np.float32), np.zeros(n)

    # --- EMIT: pixel counts per family over the selected zones
    counts = {k: np.zeros(n) for k in ["n_mesures", "n_detecte", *[f"n_{f}" for f in ALL_FAMILIES]]}
    sources = {"lithology": "GLiM (Hartmann and Moosdorf 2012)", "masks": f"MODIS MCD12C1 v061 ({args.year})"}
    if not args.no_emit:
        tables, n_granules = emit_zone_counts(ea, args)
        if tables is not None and len(tables):
            pos = pd.Index(cells).get_indexer(tables["h3"])
            keep = pos >= 0
            for k in counts:
                if k in tables:
                    counts[k] = np.bincount(pos[keep], weights=tables[k].to_numpy()[keep], minlength=n)
            sources["mineralogy"] = f"EMIT L2B MIN v001, {n_granules} granules over {len(EMIT_ZONES)} zones"
    t = assemble("earth", res, cells, counts, None, litho, litho_coverage, masks,
                 (EMIT_PIXEL_M * args.emit_step / 1000) ** 2)
    if not args.no_emit and not args.no_emit_l3:
        if fill_with_emit_l3(ea, t):
            sources["mineralogy_outside_zones"] = "EMIT L3 ASA (0.5 deg)"
    write_outputs("earth", res, t, sources)


def fill_with_emit_l3(ea, t: pd.DataFrame) -> bool:
    """Outside the EMIT L2B zones: composition from EMIT L3 ASA (mean abundances of 10 minerals on a 0.5 deg
    grid, arid regions between ~52 N and ~52 S). Each cell takes the grid box containing its center.
    These are abundances, not pixel counts: as for the Moon, the composition compares in shape only."""
    link = None
    for version in ("002", "001"):
        g = ea.search_data(short_name="EMITL3ASA", version=version)
        links = sorted(u for x in g for u in x.data_links() if u.endswith(".nc"))
        if links:
            link = links[-1]
            break
    if link is None:
        print("  EMIT L3: not found, no minerals outside the zones")
        return False
    path = fetch(ea, link, CACHE_DIR / "emit_l3")
    if path is None:
        return False
    lat, lon, abundance = read_emit_l3(path)
    step_lat, step_lon = lat[1] - lat[0], lon[1] - lon[0]
    centers = np.array([h3.cell_to_latlng(c) for c in t["h3"]])
    i = np.rint((centers[:, 0] - lat[0]) / step_lat).astype(int)
    j = np.rint((centers[:, 1] - lon[0]) / step_lon).astype(int)
    inside = (i >= 0) & (i < len(lat)) & (j >= 0) & (j < len(lon))
    i, j = np.clip(i, 0, len(lat) - 1), np.clip(j, 0, len(lon) - 1)
    family = {f: np.where(inside, a[i, j], np.nan) for f, a in abundance.items()}
    total = sum(np.nan_to_num(family[f]) for f in COMPOSITION_FAMILIES if f in family)
    to_fill = (t["source_mineralogie"].isna() & (total > 0)).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        for f in COMPOSITION_FAMILIES:
            v = np.nan_to_num(family[f]) / total if f in family else np.zeros(len(t))
            t.loc[to_fill, f"comp_{f}"] = v[to_fill].astype(np.float32)
    t.loc[to_fill, "taux_detection"] = 1.0
    t.loc[to_fill, "couverture_mineralogie"] = 1.0
    t.loc[to_fill, "source_mineralogie"] = "EMIT L3 (0.5 deg)"
    # part_oxyde_fer stays empty: L3 gives an abundance (%), not a fraction of detected pixels
    t["couverture"] = (0.5 * t["couverture_mineralogie"] + 0.5 * t["couverture_lithologie"]).astype(np.float32)
    t["fiabilite"] = t["couverture"]
    print(f"  EMIT L3: {path.name}, {int(to_fill.sum()):,} cells filled outside the zones")
    return True


def read_emit_l3(path: Path):
    """Latitudes and longitudes of the grid box centers (increasing), and abundance (%) per family (lat, lon)."""
    import netCDF4
    with netCDF4.Dataset(path) as d:
        d.set_auto_mask(False)
        names = {v.lower(): v for v in d.variables}
        lat_name = next(names[k] for k in names if k.startswith("lat"))
        lon_name = next(names[k] for k in names if k.startswith("lon"))
        lat = np.asarray(d[lat_name][:], dtype=float).ravel()
        lon = np.asarray(d[lon_name][:], dtype=float).ravel()
        abundance, read = {}, []
        for k, v in names.items():
            # *_UQ_* and *_Uncertainty variables are uncertainties, not abundances
            if "uncert" in k or "_uq" in k or v in (lat_name, lon_name) or d[v].ndim != 2:
                continue
            families = {f for mineral, f in EMIT_L3_MINERALS.items() if mineral in k}
            if len(families) != 1:
                continue
            a = np.asarray(d[v][:], dtype=float)
            if a.shape == (len(lon), len(lat)):
                a = a.T
            a[(a < 0) | (a > 100)] = np.nan                              # -9999 = no data
            f = families.pop()
            abundance[f] = np.nansum([abundance[f], a], axis=0) if f in abundance else a
            read.append(v)
    print(f"  EMIT L3: minerals read {read}")
    # The coordinates may be the upper-left corners of the boxes (multiples of 0.5 deg): move them to the centers
    step = abs(lat[1] - lat[0])
    if np.allclose(np.mod(lat, step), 0):
        lat, lon = lat - step / 2, lon + step / 2
    if lat[1] < lat[0]:
        lat = lat[::-1]
        abundance = {f: a[::-1] for f, a in abundance.items()}
    return lat, lon, abundance


def glim_classes_at(folder: Path, lat, lon) -> np.ndarray | None:
    """GLiM class rank at each point. The vector map is rasterized once (2 km, in its own projection) and
    kept in the cache; the points are read from it after reprojection."""
    import rasterio
    from pyproj import Transformer
    cache_tif = CACHE_DIR / "glim_classes_2km.tif"
    if not cache_tif.is_file():
        found = sorted(folder.rglob("*.gdb")) + sorted(folder.rglob("*.gpkg")) + sorted(folder.rglob("*.shp")) \
            if folder.is_dir() else []
        found = [s for s in found if s.suffix != ".gdb" or s.is_dir()]
        if not found:
            print(f"  GLiM: nothing in {folder}, lithology left empty (see the README)")
            return None
        import geopandas as gpd
        from rasterio import features
        from rasterio.transform import from_origin
        print(f"  GLiM: reading {found[0].name} (a few minutes, only once)...", flush=True)
        t0 = time.time()
        try:
            import pyogrio
            layers = [(name, pyogrio.read_info(found[0], layer=name).get("features", 0))
                      for name, geom in pyogrio.list_layers(found[0]) if geom and "polygon" in str(geom).lower()]
            layer = max(layers, key=lambda x: x[1])[0] if layers else None
        except Exception:                                                  # single layer: let geopandas choose
            layer = None
        gdf = gpd.read_file(found[0], layer=layer) if layer else gpd.read_file(found[0])
        field = glim_column(gdf)
        rank = gdf[field].astype(str).str.strip().str[:2].str.lower().map(class_ranks("earth")).fillna(-1).astype(int)
        print(f"  GLiM: {len(gdf):,} polygons, field '{field}', {(rank >= 0).mean():.0%} classified "
              f"({time.time() - t0:.0f} s)")
        x0, y0, x1, y1 = gdf.total_bounds
        step = 2000.0 if gdf.crs is not None and gdf.crs.is_projected else 0.02
        transform = from_origin(x0, y1, step, step)
        shape = (int(math.ceil((y1 - y0) / step)), int(math.ceil((x1 - x0) / step)))
        grid = features.rasterize(((geom, int(v)) for geom, v in zip(gdf.geometry, rank) if v >= 0 and geom is not None),
                                  out_shape=shape, transform=transform, fill=255, dtype="uint8")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with rasterio.open(cache_tif, "w", driver="GTiff", height=shape[0], width=shape[1], count=1, dtype="uint8",
                           crs=gdf.crs, transform=transform, nodata=255, compress="deflate") as dst:
            dst.write(grid, 1)
        print(f"  GLiM: rasterized into {short_path(cache_tif, ROOT)} ({time.time() - t0:.0f} s)")
        del gdf
    with rasterio.open(cache_tif) as r:
        grid, transform, crs = r.read(1), r.transform, r.crs
    x, y = (lon, lat) if crs is None or not crs.is_projected else \
        Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(lon, lat)
    row = ((transform.f - np.asarray(y)) / -transform.e).astype(np.int64)
    col = ((np.asarray(x) - transform.c) / transform.a).astype(np.int64)
    inside = (row >= 0) & (row < grid.shape[0]) & (col >= 0) & (col < grid.shape[1])
    v = np.full(len(lat), -1, dtype=np.int16)
    v[inside] = grid[row[inside], col[inside]]
    v[v == 255] = -1
    return v


def unit_column(gdf, codes, first_two_letters: bool = False) -> str:
    """Field whose values are most often known map unit codes."""
    best, score = None, 0.0
    for c in gdf.columns:
        if c == "geometry":
            continue
        v = gdf[c].dropna().astype(str).str.strip()
        if first_two_letters:
            v = v.str[:2].str.lower()
        s = v.isin(codes).mean() if len(v) else 0.0
        if s > score:
            best, score = c, s
    if best is None or score < 0.5:
        sys.exit(f"No map unit field recognized among {list(gdf.columns)}")
    return best


def glim_column(gdf) -> str:
    """Field holding the GLiM class ("xx", "Litho"...): the one whose first two letters are most often a
    first-level GLiM code ("wb" water bodies and "nd" no data included)."""
    return unit_column(gdf, set(class_ranks("earth")) | {"wb", "nd"}, first_two_letters=True)


def emit_zone_counts(ea, args: argparse.Namespace):
    """EMIT counts per cell over EMIT_ZONES: for each zone, the --emit-max least cloudy (then most recent)
    granules are downloaded (mineral file only, not the uncertainty one), read, then deleted."""
    tables, seen = [], set()
    for zone in EMIT_ZONES:
        g = ea.search_data(short_name="EMITL2BMIN", version="001",
                           bounding_box=(zone.west, zone.south, zone.east, zone.north))
        n_max = zone.max_granules or args.emit_max
        # Least cloudy scenes first (cloud cover from the metadata), then the most recent ones
        scenes = []
        for x in g:
            try:
                cloud = float((x.get("umm") or {}).get("CloudCover"))
            except (TypeError, ValueError, AttributeError):
                cloud = 100.0
            for u in x.data_links():
                if "L2B_MIN_" in u and "UNC" not in u and u.endswith(".nc"):
                    scenes.append((cloud, u))
        scenes.sort(key=lambda s: (s[0], [-ord(c) for c in s[1].rsplit("/", 1)[-1]]))
        links = list(dict.fromkeys(u for _, u in scenes if u not in seen))[:n_max]
        clouds = [c for c, u in scenes if u in links and c < 100]
        print(f"  EMIT {zone.name}: {len(g)} granules found, {len(links)} read"
              + (f" (clouds {min(clouds):.0f} to {max(clouds):.0f} %)" if clouds else ""), flush=True)
        for link in links:
            seen.add(link)
            path = fetch(ea, link, CACHE_DIR / "emit")
            if path is None:
                continue
            try:
                tables.append(granule_counts(path, resolution=args.resolution, step=args.emit_step))
            except (OSError, KeyError, ValueError, ImportError, RuntimeError) as e:
                print(f"    {path.name} unreadable ({type(e).__name__}: {e}), skipped")
            finally:
                path.unlink(missing_ok=True)
    return (merge_counts(tables) if tables else None), len(seen)


# ------------------------------------------------------------------ Mars
def process_mars(args: argparse.Namespace) -> None:
    print("\n=== Mars")
    res = args.resolution
    cells, lat_c, lon_c = global_cells(res)
    n = len(cells)
    print(f"  {n:,} H3 cells at resolution {res}")
    sources = {}

    # --- OMEGA: detections per 0.1 deg block (4 x 4 pixels)
    maps = {}
    for key, (folder, name) in OMEGA_MAPS.items():
        if all(download(OMEGA_URL.format(folder=folder, name=f"{name}.{ext}"), CACHE_DIR / "omega" / f"{name}.{ext}")
               for ext in ("LBL", "IMG")):
            maps[key] = CACHE_DIR / "omega" / name
    if set(OMEGA_MAPS) <= set(maps):
        blocks, lat_b, lon_b, km2_per_pixel = omega_blocks(maps)
        counts = sum_blocks_per_cell(blocks, lat_b, lon_b, cells, lat_c, lon_c, res)
        sources["mineralogy"] = "OMEGA DDR global maps (Ody et al. 2012), table 3 thresholds"
    else:
        print("  OMEGA incomplete: mineral composition left empty (see the README)")
        counts = {"n_mesures": np.zeros(n), "n_detecte": np.zeros(n)}
        km2_per_pixel = 1.0
    for f in MINERAL_FAMILIES:
        counts.setdefault(f"n_{f}", np.zeros(n))

    # --- SIM 3292 geologic map
    gdf = load_mars_map(args.mars_map)
    if gdf is None:
        litho, coverage = np.full((n, len(ROCK_CLASSES)), np.nan, np.float32), np.zeros(n)
    else:
        litho, coverage = map_lithology(gdf, "mars", cells)
        sources["lithology"] = "USGS SIM 3292 (Tanaka et al. 2014)"
    t = assemble("mars", res, cells, counts, None, litho, coverage, None, km2_per_pixel)
    write_outputs("mars", res, t, sources)


def read_pds_label(path: Path) -> dict:
    """Dimensions and encoding of a PDS3 image from its .LBL label."""
    text = path.read_text(encoding="latin-1")

    def value(key: str) -> str:
        return re.search(rf"^\s*{key}\s*=\s*([^\s<]+)", text, re.M).group(1).strip('"')

    return {"lines": int(value("LINES")), "samples": int(value("LINE_SAMPLES")),
            "missing": int(float(value("MISSING_CONSTANT"))), "scale": float(value("SCALING_FACTOR")),
            "offset": float(value("OFFSET")), "ppd": float(value("MAP_RESOLUTION")),
            "type": value("SAMPLE_TYPE"), "bits": int(value("SAMPLE_BITS"))}


def omega_blocks(maps: dict, size: int = 4):
    """Read the OMEGA maps by bands and count, per block of size x size pixels, the measured pixels and the
    detections of each family. Returns the blocks, their center lat/lon and the km2 of a pixel at the equator."""
    labels = {k: read_pds_label(p.with_suffix(".LBL")) for k, p in maps.items()}
    ref = labels["pyroxene"]
    if any((v["lines"], v["samples"]) != (ref["lines"], ref["samples"]) for v in labels.values()):
        raise ValueError("OMEGA maps of different sizes")
    dtype = np.dtype("<i2" if "LSB" in ref["type"] else ">i2")
    images = {k: np.memmap(p.with_suffix(".IMG"), dtype=dtype, mode="r", shape=(ref["lines"], ref["samples"]))
              for k, p in maps.items()}
    nl, nc = ref["lines"] // size, ref["samples"] // size
    names = ["n_mesures", "n_detecte", "n_olivine", "n_pyroxene", "n_oxyde_fer"]
    blocks = {k: np.zeros((nl, nc), np.float32) for k in names}
    blocks["n_pixels"] = np.full((nl, nc), size * size, np.float32)       # pixels read, measured or not

    def physical(key, a):
        return np.where(a == labels[key]["missing"], np.nan, a * labels[key]["scale"] + labels[key]["offset"])

    rows_per_band = 100 * size
    for start in range(0, nl * size, rows_per_band):
        stop = min(start + rows_per_band, nl * size)
        v = {k: physical(k, np.asarray(m[start:stop, : nc * size], dtype=np.float32)) for k, m in images.items()}
        measured = np.isfinite(v["ferric"])                               # Fe3+: defined wherever OMEGA measured
        olivine = np.nan_to_num(v["olivine"], nan=-1) >= OMEGA_THRESHOLDS["olivine"]
        pyroxene = np.nan_to_num(v["pyroxene"], nan=-1) >= OMEGA_THRESHOLDS["pyroxene"]
        ferric = np.nan_to_num(v["ferric"], nan=-1) >= OMEGA_THRESHOLDS["ferric"]
        detected = olivine | pyroxene | ferric
        rows = slice(start // size, stop // size)
        for k, a in zip(names, (measured, detected & measured, olivine & measured, pyroxene & measured,
                                ferric & measured)):
            blocks[k][rows] = a.astype(np.float32).reshape((stop - start) // size, size, nc, size).sum(axis=(1, 3))
    ppd = ref["ppd"]
    lat_b = 90 - (np.arange(nl) + 0.5) * size / ppd
    lon_b = -180 + (np.arange(nc) + 0.5) * size / ppd
    print(f"  OMEGA: {ref['lines']} x {ref['samples']} pixels ({ppd:g} per degree), "
          f"{blocks['n_mesures'].sum() / (ref['lines'] * ref['samples']):.0%} measured")
    return blocks, lat_b, lon_b, (math.radians(1 / ppd) * RADIUS_KM["mars"]) ** 2


def load_mars_map(folder: Path):
    """SIM 3292 map: a local file in `folder` if any, otherwise downloaded once as GeoJSON into the cache."""
    import geopandas as gpd
    local = [f for f in sorted(folder.rglob("*")) if f.suffix.lower() in (".shp", ".gpkg", ".geojson", ".json")] \
        if folder.is_dir() else []
    if local:
        gdf = gpd.read_file(local[0])
    else:
        target = CACHE_DIR / "carte_mars_sim3292.geojson"
        if not target.is_file():
            features = None
            for template in MARS_MAP_URLS:
                features = []
                try:
                    for start in range(0, 20000, 1000):
                        with urllib.request.urlopen(template.format(n=1000, start=start), timeout=120) as r:
                            page = json.load(r).get("features", [])
                        features += page
                        if len(page) < 1000:
                            break
                    if features:
                        break
                except (OSError, ValueError) as e:
                    print(f"  Mars map: {template.split('/')[2]} unavailable ({e})")
                    features = None
            if not features:
                print(f"  Mars map not found: put it in {folder} (see the README)")
                return None
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
            print(f"  Mars map: {len(features):,} units downloaded")
        gdf = gpd.read_file(target)
    if gdf.crs is not None and gdf.crs.is_projected:
        gdf = gdf.to_crs(gdf.crs.geodetic_crs)
    return gdf


# ------------------------------------------------------------------ Moon
def process_moon(args: argparse.Namespace) -> None:
    print("\n=== Moon")
    res = args.resolution
    cells, lat_c, lon_c = global_cells(res)
    n = len(cells)
    print(f"  {n:,} H3 cells at resolution {res}")
    sources = {}

    # --- Mineral abundances (Lucey et al. 2021), per block of 4 x 4 pixels
    files = {name: CACHE_DIR / "lune" / f"diviner_MI_{name}.tiff" for name in [*MOON_MINERALS, "latitude", "longitude"]}
    available = {k: f for k, f in files.items() if download(MOON_URL.format(name=k), f)}
    if set(MOON_MINERALS) <= set(available):
        blocks, lat_b, lon_b, km2_per_pixel = moon_blocks(available)
        per_cell = sum_blocks_per_cell(blocks, lat_b, lon_b, cells, lat_c, lon_c, res)
        measured = per_cell["n_mesures"]
        with np.errstate(invalid="ignore", divide="ignore"):
            abundances = {family: np.where(measured > 0, per_cell[mineral] / measured, 0.0)
                          for mineral, family in MOON_MINERALS.items()}
        abundances["n_mesures"] = measured
        abundances["n_pixels"] = per_cell["n_pixels"]
        sources["mineralogy"] = "Lucey et al. 2021, Zenodo 4558194 (Kaguya MI + Diviner)"
    else:
        print("  mineral abundances unavailable: composition left empty (see the README)")
        abundances = {"n_mesures": np.zeros(n), **{f: np.zeros(n) for f in MOON_MINERALS.values()}}
        km2_per_pixel = 1.0
    for f in MINERAL_FAMILIES:
        abundances.setdefault(f, np.zeros(n))

    # --- Unified Geologic Map of the Moon (USGS 2020)
    import geopandas as gpd
    shp = [f for f in sorted(args.moon_map.rglob("*.shp")) if "geounit" in f.stem.lower()] \
        if args.moon_map.is_dir() else []
    if not shp:
        print(f"  Moon map: no GeoUnits.shp in {args.moon_map}, lithology left empty (see the README)")
        litho, coverage = np.full((n, len(ROCK_CLASSES)), np.nan, np.float32), np.zeros(n)
    else:
        gdf = gpd.read_file(shp[0])
        if gdf.crs is not None and gdf.crs.is_projected:
            gdf = gdf.to_crs(gdf.crs.geodetic_crs)
        litho, coverage = map_lithology(gdf, "moon", cells)
        sources["lithology"] = "USGS Unified Geologic Map of the Moon (2020)"
    t = assemble("moon", res, cells, None, abundances, litho, coverage, None, km2_per_pixel)
    write_outputs("moon", res, t, sources)


def moon_blocks(files: dict, size: int = 4):
    """Sum of the abundances and number of valid pixels per block of size x size pixels. Returns the
    blocks, their center lat/lon and the km2 of a pixel at the equator."""
    import rasterio

    def read(key: str) -> np.ndarray:
        with rasterio.open(files[key]) as src:
            return src.read(1).astype(np.float32)

    with rasterio.open(files["olivine"]) as ref:
        height, width, transform = ref.height, ref.width, ref.transform
        georeferenced = ref.crs is not None and not transform.is_identity
    nl, nc = height // size, width // size

    def crop(a):
        return a[: nl * size, : nc * size]

    def block_sum(a):
        return crop(a).reshape(nl, size, nc, size).sum(axis=(1, 3))

    values = {k: read(k) for k in MOON_MINERALS}
    scale = 100.0 if max(np.nanmax(v) for v in values.values()) > 1.5 else 1.0   # % -> fraction if needed
    valid = np.ones((height, width), bool)
    for v in values.values():
        valid &= np.isfinite(v) & (v >= 0) & (v <= 1.5 * scale)
    blocks = {"n_mesures": block_sum(valid.astype(np.float32)), "n_pixels": np.full((nl, nc), size * size, np.float32)}
    for k, v in values.items():
        blocks[k] = block_sum(np.where(valid, v / scale, 0).astype(np.float32))
    if georeferenced:
        lat_b = transform.f + transform.e * (np.arange(nl) * size + size / 2)
        lon_b = transform.c + transform.a * (np.arange(nc) * size + size / 2)
    else:
        lat_b = crop(read("latitude")).reshape(nl, size, nc, size).mean(axis=(1, 3))[:, 0]
        lon_b = crop(read("longitude")).reshape(nl, size, nc, size).mean(axis=(1, 3))[0, :]
    lon_b = (lon_b + 180) % 360 - 180
    if np.any(np.diff(lon_b) < 0):                                         # 0..360 grid: put it back in order
        order = np.argsort(lon_b)
        lon_b = lon_b[order]
        blocks = {k: v[:, order] for k, v in blocks.items()}
    print(f"  abundances: {width} x {height} pixels, latitudes {lat_b.min():.1f} to {lat_b.max():.1f}, "
          f"{blocks['n_mesures'].sum() / (width * height):.0%} valid")
    step_deg = abs(lon_b[1] - lon_b[0]) / size
    return blocks, lat_b, lon_b, (math.radians(step_deg) * RADIUS_KM["moon"]) ** 2


def main() -> int:
    args = parse_args()
    t0 = time.time()
    for body, process in (("moon", process_moon), ("mars", process_mars), ("earth", process_earth)):
        if body in args.bodies:
            process(args)
    print(f"\nDone in {(time.time() - t0) / 60:.1f} min.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
