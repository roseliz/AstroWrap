"""Phase 1: calibration granules over the reference zones (sites.CALIBRATION_ZONES).

For each zone: the --n-v002 v002 granules and the --n-v001 v001 granules, among the least cloudy, that cover
the most cells of the zone (both versions, to calibrate thresholds specific to each).
Output: cache/mineralogie_terre/calibration/liste.parquet
"""

from __future__ import annotations

import argparse

from sites import zones_table
from utils import CALIBRATION_DIR, CATALOG_DIR, duckdb_h3


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--n-v002", type=int, default=6, help="v002 granules per zone (default: 6)")
    p.add_argument("--n-v001", type=int, default=4, help="v001 granules per zone (default: 4)")
    p.add_argument("--max-clouds", type=float, default=30, help="maximum announced cloud cover, %% (default: 30)")
    args = p.parse_args()
    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
    raw_list = (CALIBRATION_DIR / "liste_brute.parquet").as_posix()
    final_list = (CALIBRATION_DIR / "liste.parquet").as_posix()
    c = duckdb_h3()
    c.register("zones", zones_table())
    c.execute("""CREATE TABLE z AS
        SELECT nom, unnest(CASE WHEN len(cs) > 0 THEN cs ELSE [h3_latlng_to_cell((sud+nord)/2, (ouest+est)/2, 5)] END) AS cell
        FROM (SELECT *, h3_polygon_wkt_to_cells('POLYGON((' || ouest || ' ' || sud || ',' || est || ' ' || sud || ',' ||
              est || ' ' || nord || ',' || ouest || ' ' || nord || ',' || ouest || ' ' || sud || '))', 5) AS cs
              FROM zones)""")
    c.execute(f"""CREATE TABLE g AS SELECT * FROM read_parquet('{CATALOG_DIR.as_posix()}/granules_*.parquet')
                  WHERE coalesce(nuages, 100) <= {args.max_clouds}""")
    c.execute("""CREATE TABLE gc AS SELECT granule, unnest(h3_polygon_wkt_to_cells('POLYGON((' || array_to_string(
                 list_transform(CAST(emprise AS DOUBLE[2][]), p -> p[1] || ' ' || p[2]), ', ') || '))', 5)) AS cell FROM g""")
    c.execute(f"""COPY (
        WITH r AS (SELECT z.nom AS zone, g.*, count(*) AS n_cellules_zone FROM z JOIN gc USING (cell) JOIN g USING (granule)
                   GROUP BY ALL),
             k AS (SELECT *, row_number() OVER (PARTITION BY zone, version ORDER BY n_cellules_zone DESC, nuages, debut DESC) rk FROM r)
        SELECT * EXCLUDE (rk) FROM k
        WHERE (version = '002' AND rk <= {args.n_v002}) OR (version = '001' AND rk <= {args.n_v001})
        ORDER BY zone, version DESC, rk) TO '{raw_list}' (FORMAT parquet)""")
    # A granule can serve two neighboring zones: it is processed only once
    c.execute(f"""COPY (SELECT * FROM read_parquet('{raw_list}')
                  QUALIFY row_number() OVER (PARTITION BY granule ORDER BY zone) = 1)
                  TO '{final_list}' (FORMAT parquet)""")
    print(c.execute(f"""SELECT zone, count(*) FILTER (version='002') v002, count(*) FILTER (version='001') v001,
                        round(median(nuages)) median_clouds, round(sum(octets_min + octets_unc + 47e6)/1e9, 1) gb
                        FROM read_parquet('{final_list}') GROUP BY zone ORDER BY zone""").df().to_string(index=False))
    n, gb = c.execute(f"SELECT count(*), round(sum(octets_min + octets_unc + 47e6)/1e9) FROM read_parquet('{final_list}')").fetchone()
    print(f"{n} granules, ~{gb:.0f} GB")


if __name__ == "__main__":
    main()
