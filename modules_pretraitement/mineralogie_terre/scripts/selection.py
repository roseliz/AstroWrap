"""Phase 0: granules -> H3 cells (resolution 5), then the K best granules per cell.

1. Versions read (--versions, default: v002 only). On the same cells, v001 detects 4 to 25 times more micas,
   carbonates and clays than v002 (phase 1), so the two are not mixed. When several versions are requested,
   an acquisition is kept only once, in its most recent version.
2. Cells kept: the arid zone mapped by EMIT, that is the 0.5 deg EMIT L3 ASA boxes that have a measurement
   (see l3.py), converted into H3 cells. Outside this zone, EMIT mostly sees vegetation or clouds.
3. A cell belongs to a granule when its center falls inside the granule footprint (DuckDB h3 extension).
4. Granules that are too cloudy are dropped (--max-clouds, cloud cover announced in CMR).
5. Ranking per cell: fewer clouds, then v002 before v001, then higher sun, then more recent.
   Ranks 1 to K are kept; cutting to a smaller K later = filtering on `rang`.

Outputs (cache/mineralogie_terre/catalogue/):
  cellules_granules.parquet  h3, granule, version, rang
  selection.parquet          granules kept, with their best rank and the number of cells where they count
"""

from __future__ import annotations

import argparse

import l3
from utils import CATALOG_DIR, duckdb_h3

MASK_BYTES = 47e6        # typical size of the L2A mask (missing from the L2B metadata)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-k", type=int, default=5, help="granules kept per cell (default: 5)")
    p.add_argument("--versions", nargs="+", default=["002"], help="EMIT L2B versions (default: 002)")
    p.add_argument("--max-clouds", type=float, default=30, help="maximum announced cloud cover, %% (default: 30)")
    p.add_argument("--resolution", type=int, default=5, help="H3 resolution (default: 5)")
    args = p.parse_args()
    r = args.resolution
    c = duckdb_h3()
    c.register("aride_txt", l3.arid_cells(r, c))
    c.execute("CREATE TABLE aride AS SELECT h3_string_to_h3(h3) AS cell FROM aride_txt")
    files = ", ".join(f"'{(CATALOG_DIR / f'granules_{v}.parquet').as_posix()}'" for v in args.versions)
    c.execute(f"""CREATE TABLE g AS
        WITH t AS (SELECT *, regexp_extract(granule, '_(\\d{{8}}T\\d{{6}})', 1) AS acquisition
                   FROM read_parquet([{files}]))
        SELECT * EXCLUDE (r) FROM (SELECT *, row_number() OVER (PARTITION BY acquisition ORDER BY version DESC) r FROM t)
        WHERE r = 1""")
    c.execute(f"""CREATE TABLE rg AS
        WITH cg AS (
            SELECT granule, version, nuages, zenith_solaire, debut,
                   unnest(h3_polygon_wkt_to_cells('POLYGON((' || array_to_string(list_transform(
                       CAST(emprise AS DOUBLE[2][]), p -> p[1] || ' ' || p[2]), ', ') || '))', {r})) AS cell
            FROM g WHERE coalesce(nuages, 100) <= {args.max_clouds})
        SELECT h3_h3_to_string(cell) AS h3, granule, version, rang FROM (
            SELECT cg.*, row_number() OVER (PARTITION BY cell ORDER BY coalesce(nuages, 100), version DESC,
                   zenith_solaire, debut DESC) AS rang
            FROM cg JOIN aride USING (cell))
        WHERE rang <= {args.k}""")
    c.execute(f"COPY rg TO '{(CATALOG_DIR / 'cellules_granules.parquet').as_posix()}' (FORMAT parquet)")
    c.execute(f"""COPY (SELECT g.*, s.rang_min, s.n_cellules FROM g JOIN
                  (SELECT granule, min(rang) rang_min, count(*) n_cellules FROM rg GROUP BY granule) s USING (granule))
                  TO '{(CATALOG_DIR / 'selection.parquet').as_posix()}' (FORMAT parquet)""")
    n_arid = c.execute("SELECT count(*) FROM aride").fetchone()[0]
    print(f"EMIT arid zone: {n_arid:,} H3 r{r} cells; clouds <= {args.max_clouds:.0f} %")
    for k in range(args.k, 0, -1):
        n, n2, size, cells = c.execute(f"""
            WITH s AS (SELECT DISTINCT rg.granule, rg.version FROM rg WHERE rang <= {k})
            SELECT count(*), sum((s.version = '002')::INT), sum(g.octets_min + g.octets_unc) + count(*) * {MASK_BYTES},
                   (SELECT count(DISTINCT h3) FROM rg)
            FROM s JOIN g USING (granule)""").fetchone()
        print(f"  K={k}: {n:7,} granules (v002 {n2:,}), {cells:,} cells covered, "
              f"full MIN+UNC+mask files ~{size / 1e12:.1f} TB ({size / n / 1e6:.0f} MB/granule)")


if __name__ == "__main__":
    main()
