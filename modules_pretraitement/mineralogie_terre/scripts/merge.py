"""Per-granule counts -> final table per H3 r5 cell (pretreatment_data/mineralogie_terre/).

  python merge.py --counts <folder> [--output <folder>] [--suffix _test]

The folder holds pairs <granule>_cellules.parquet / <granule>_histo.parquet: either the production output of
batch.py (--production, resolution 5), or the full output (calibration, any resolution >= 5: the mask and
thresholds of thresholds.py are applied here and the cells are brought to resolution 5; counts add up exactly).

Columns (one row per cell of the EMIT arid zone, and per cell observed outside it by granule edges):
  det_<family>_<level>  fraction of the valid pixels where the family is detected (level faible / moyen /
                        fort: band depth >= 2, 3 or 5 times its uncertainty). NaN when no pixel is valid.
  bd_<family>           mean band depth of the pixels detected at the medium level (NaN if none)
  n_valides, n_total    valid pixels (SpecTf, cirrus, water mask) and geolocated pixels, all granules
  n_granules            granules touching the cell
  zone_aride            cell of the EMIT arid zone (center in a measured L3 box): the only zone where the
                        granules were chosen (the 5 best); outside, granules were chosen for neighboring cells
  couverture            fraction of the cell seen in valid pixels by its best granule (60 m pixels, capped
                        at 1). Recommended quality filter for comparisons: couverture >= 0.5
  ab_l3_<family>        EMIT L3 spectral abundance of the 0.5 deg box containing the cell center (sum of the
                        family's minerals, not renormalized; a different quantity from det_*)
  id_case_l3            L3 box used ("lat_lon" of its center)
  source                L2B (at least one valid pixel), L3 (L3 abundance only), vide (empty)
  resolution_source_m   60 (L2B), 55000 (L3), NaN (empty)
  id_case_source        id_case_l3 when source = L3, otherwise empty
No renormalization; NaN = not measured.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import h3
import numpy as np
import pandas as pd

import l3
from families import FAMILIES
from granule import FIT_BINS, MASKS, SNR_BINS, WEIGHT_BINS
from sites import AUDIT_SITES
from thresholds import LEVELS, thresholds_table
from utils import CACHE_DIR, MODULE, OUTPUT_DIR, duckdb_h3, rebuild_duckdb, short_path

RES = 5
PIXEL_M2 = 60.0 * 60.0          # nominal EMIT pixel


def load_thresholds() -> pd.DataFrame:
    """thresholds.py as a table, with the SNR class matching each min_snr."""
    s = thresholds_table()
    s["classe_snr"] = [int(np.searchsorted(SNR_BINS, v)) for v in s.snr_min]
    if any(SNR_BINS[k] != v for k, v in zip(s.classe_snr, s.snr_min)):
        raise ValueError("thresholds.py: min_snr must be one of granule.SNR_BINS")
    return s


def load_counts(c, folder: Path, thresholds: pd.DataFrame) -> None:
    """Tables `cel` (h3, granule, n_total, n_valides) and `his` (h3, famille, snrbin, n, bd) at resolution 5."""
    d = folder.as_posix()
    columns = c.execute(f"SELECT * FROM read_parquet('{d}/*_cellules.parquet') LIMIT 0").df().columns
    full = "drap" in columns
    res_read = c.execute(f"SELECT h3_get_resolution(h3_string_to_h3(h3)) FROM read_parquet('{d}/*_cellules.parquet') "
                         "LIMIT 1").fetchone()[0]
    versions = ", ".join(f"'{v}'" for v in thresholds.version.unique())
    keep = f"version IN ({versions})"               # only the calibrated versions
    if res_read == RES:
        def parent(x):
            return x
    else:
        def parent(x):
            return f"h3_h3_to_string(h3_cell_to_parent(h3_string_to_h3({x}), {RES}))"
    if full:
        bits = MASKS[thresholds.masque.iloc[0]]
        wmin = int(np.searchsorted(WEIGHT_BINS, thresholds.poids_min.min()))
        fmin = int(np.searchsorted(FIT_BINS, thresholds.fit_min.min()))
        c.execute(f"""CREATE TABLE cel AS SELECT {parent('h3')} h3, granule, sum(n) n_total,
                      sum(n) FILTER ((drap & {bits}) = 0) n_valides
                      FROM read_parquet('{d}/*_cellules.parquet') WHERE {keep} GROUP BY ALL""")
        c.execute(f"""CREATE TABLE his AS SELECT {parent('h3')} h3, famille, snrbin, sum(n) n, sum(bd) bd
                      FROM read_parquet('{d}/*_histo.parquet')
                      WHERE {keep} AND (drap & {bits}) = 0 AND wbin >= {wmin} AND fitbin >= {fmin} GROUP BY ALL""")
    else:
        c.execute(f"""CREATE TABLE cel AS SELECT {parent('h3')} h3, granule, sum(n_total) n_total, sum(n_valides) n_valides
                      FROM read_parquet('{d}/*_cellules.parquet') WHERE {keep} GROUP BY ALL""")
        c.execute(f"""CREATE TABLE his AS SELECT {parent('h3')} h3, famille, snrbin, sum(n) n, sum(bd) bd
                      FROM read_parquet('{d}/*_histo.parquet') WHERE {keep} GROUP BY ALL""")


def detection_table(c, thresholds: pd.DataFrame) -> pd.DataFrame:
    """Per-cell totals, coverage, and det_* / bd_* columns of every family."""
    totals = c.execute(f"""SELECT h3, sum(n_total) n_total, coalesce(sum(n_valides), 0) n_valides,
                       count(DISTINCT granule) n_granules,
                       least(1, max(coalesce(n_valides, 0) * {PIXEL_M2} / h3_cell_area(h3_string_to_h3(h3), 'm^2'))) couverture
                       FROM cel GROUP BY h3""").df()
    medium = int(thresholds.loc[thresholds.niveau == "moyen", "classe_snr"].iloc[0])
    counts = ", ".join(f"sum(n) FILTER (snrbin >= {int(r.classe_snr)}) AS n_{r.niveau}" for r in thresholds.itertuples())
    d = c.execute(f"""SELECT h3, famille, {counts}, sum(bd) FILTER (snrbin >= {medium}) bd_moyen
                      FROM his GROUP BY ALL""").df()
    t = totals.set_index("h3")
    n_valid = t["n_valides"].astype(float).where(t["n_valides"] > 0)
    for f in FAMILIES:
        x = d[d.famille == f].set_index("h3").reindex(t.index)
        for level in LEVELS:
            t[f"det_{f}_{level}"] = (x[f"n_{level}"].fillna(0) / n_valid).astype("float32")
        t[f"bd_{f}"] = (x["bd_moyen"] / x["n_moyen"].where(x["n_moyen"] > 0)).where(n_valid.notna()).astype("float32")
    return t.reset_index()


def check_audit_sites(t: pd.DataFrame) -> None:
    """Print the value of each independent reference site (sites.AUDIT_SITES) against its expected range."""
    values = t.set_index("h3")
    print("Audit reference sites (never used for calibration):")
    for site, lat, lon, column, low, high, source in AUDIT_SITES:
        cell = h3.latlng_to_cell(lat, lon, RES)
        v = float(values.at[cell, column]) if cell in values.index else np.nan
        status = "missing" if np.isnan(v) else ("ok" if low <= v <= high else "OUT OF RANGE")
        print(f"  {status:12s} {site:18s} {column:22s} {v:6.3f}  expected [{low:g}, {high:g}]  ({source})")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--counts", type=Path, default=CACHE_DIR / "resultats",
                   help="folder of the per-granule counts (default: cache/mineralogie_terre/resultats, local copy "
                        "of the S3 bucket)")
    p.add_argument("--output", type=Path, default=OUTPUT_DIR)
    p.add_argument("--suffix", default="", help="added to the file name (e.g. _test)")
    p.add_argument("--arid-zone", action=argparse.BooleanOptionalAction, default=True,
                   help="add the arid-zone cells without any L2B observation (default: yes)")
    args = p.parse_args()
    t0 = time.time()
    thresholds = load_thresholds()
    c = duckdb_h3()
    load_counts(c, args.counts, thresholds)
    t = detection_table(c, thresholds)
    n_granules = c.execute("SELECT count(DISTINCT granule) FROM cel").fetchone()[0]
    g = l3.read_l3()
    arid = l3.arid_cells(RES, c, g)
    if args.arid_zone:
        t = arid.assign(zone_aride=True).merge(t, on="h3", how="outer")
        t["zone_aride"] = t["zone_aride"].eq(True)
    else:
        t["zone_aride"] = t["h3"].isin(arid["h3"])
    for k in ("n_total", "n_valides", "n_granules"):
        t[k] = t[k].fillna(0).astype("int64")
    t["couverture"] = t["couverture"].fillna(0).astype("float32")
    t = t[t.zone_aride | (t.n_valides > 0)]          # outside the zone: observed cells only (not the sea)
    centers = c.execute("SELECT h3_cell_to_lat(h3_string_to_h3(x)), h3_cell_to_lng(h3_string_to_h3(x)) "
                        "FROM (SELECT unnest(?) x)", [t["h3"].tolist()]).fetchnumpy()
    points = l3.sample_points(*[np.asarray(v) for v in centers.values()], g)
    t = pd.concat([t.reset_index(drop=True), points], axis=1)
    has_l3 = t[[f"ab_l3_{f}" for f in FAMILIES]].notna().any(axis=1)
    t["source"] = np.where(t.n_valides > 0, "L2B", np.where(has_l3, "L3", "vide"))
    t["resolution_source_m"] = np.select([t.source == "L2B", t.source == "L3"], [60.0, float(l3.RESOLUTION_M)], np.nan)
    t["id_case_source"] = np.where(t.source == "L3", t.id_case_l3, None)
    t.insert(0, "resolution", RES)
    t.insert(0, "body", "earth")
    order = (["body", "resolution", "h3"] + [f"det_{f}_{n}" for f in FAMILIES for n in LEVELS]
             + [f"bd_{f}" for f in FAMILIES] + ["n_valides", "n_total", "n_granules", "zone_aride", "couverture"]
             + [f"ab_l3_{f}" for f in FAMILIES] + ["id_case_l3", "source", "resolution_source_m", "id_case_source"])
    t = t[order].sort_values("h3").reset_index(drop=True)
    for k in [f"ab_l3_{f}" for f in FAMILIES] + ["resolution_source_m"]:
        t[k] = t[k].astype("float32")

    import pyarrow as pa
    import pyarrow.parquet as pq
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / f"{MODULE}_earth_h3_{RES}{args.suffix}.parquet"
    meta = {"module": MODULE, "body": "earth", "families": json.dumps(FAMILIES),
            "thresholds": thresholds.drop(columns="classe_snr").to_json(orient="records"),
            "sources": json.dumps({"mineralogy": f"EMIT L2B MIN v002 ({n_granules} granules), L2A mask v003",
                                   "l3_abundance": "EMIT L3 ASA v002 (0.5 deg)"})}
    table = pa.Table.from_pandas(t, preserve_index=False)
    table = table.replace_schema_metadata({**(table.schema.metadata or {}), **{k: v.encode() for k, v in meta.items()}})
    pq.write_table(table, path, compression="zstd")
    rebuild_duckdb(args.output, "earth")
    print(f"{len(t):,} cells -> {short_path(path)} ({path.stat().st_size / 1e6:.1f} MB, {time.time() - t0:.0f} s)")
    print("cells per source:", t.source.value_counts().to_dict())
    print("arid zone:", t.zone_aride.value_counts().to_dict(), "; couverture >= 0.5:",
          t.groupby("zone_aride").couverture.apply(lambda x: f"{(x >= 0.5).mean():.1%}").to_dict())
    print(t.loc[t.source == "L2B", [f"det_{f}_moyen" for f in FAMILIES]].describe().round(3).to_string())
    check_audit_sites(t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
