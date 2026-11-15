"""Phase 1: detection thresholds, evaluated on the counts of the calibration granules and checked on the
reference sites (sites.CALIBRATION_SITES).

A detection is kept when: weight of the family in the library entry >= 0.1 (only traces are dropped: this
weight measures the share of the mineral in the reference sample, not the confidence of the detection),
fit score >= min_fit, band depth / uncertainty (snr) >= min_snr, and pixel accepted by the chosen mask.

Two methods, compared on the same reference sites:
  statistical: levels fixed in advance on snr (weak >= 2, medium >= 3, strong >= 5 times the uncertainty),
               not tuned on the sites; the sites are only used to check them.
  tuned:       sweep of min_fit and min_snr; at each level, worst false alarm ("absent" sites)
               <= 15 / 5 / 1 %, and the highest minimum detection on the "present" sites.
Thresholds are specific to each version (v001, v002) and to each Tetracorder group (1: iron oxides, 1 um
band; 2: the other families, bands near 2.2 to 2.3 um).

The thresholds used by the processing are frozen in thresholds.py: this script only reports candidates
(cache/mineralogie_terre/calibration/seuils_candidats.csv) and a leave-one-site-out validation.

  python calibration.py [--counts <folder>] [--resolution 7]
"""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

from granule import FIT_BINS, MASKS, SNR_BINS, WEIGHT_BINS
from sites import calibration_sites_table, zones_table
from utils import CALIBRATION_DIR, duckdb_h3

LEVELS = {"fort": 0.01, "moyen": 0.05, "faible": 0.15}        # maximum false alarm per level (tuned method)
STATISTICAL = {"faible": 2.0, "moyen": 3.0, "fort": 5.0}      # snr per level (statistical method)
GROUP_1_FAMILIES = ["oxyde_fer"]
MIN_WEIGHT = 0.1


def connect(folder: Path, res: int = 7):
    """DuckDB views of the calibration counts, and the H3 cells of each reference site at resolution `res`."""
    c = duckdb_h3()
    c.execute(f"CREATE VIEW cel AS SELECT * FROM read_parquet('{folder.as_posix()}/*_cellules.parquet')")
    c.execute(f"CREATE VIEW his AS SELECT * FROM read_parquet('{folder.as_posix()}/*_histo.parquet')")
    c.register("z", zones_table())
    c.register("t", calibration_sites_table())

    def box(w, s, e, n):
        return (f"'POLYGON((' || {w} || ' ' || {s} || ',' || {e} || ' ' || {s} || ',' || {e} || ' ' || {n} || ',' || "
                f"{w} || ' ' || {n} || ',' || {w} || ' ' || {s} || '))'")

    # Cells of each site: those of its box, or of its whole zone
    c.execute(f"""CREATE TABLE tc AS
        SELECT DISTINCT site, famille, attendu,
               h3_h3_to_string(unnest(h3_polygon_wkt_to_cells({box('t.ouest', 't.sud', 't.est', 't.nord')}, {res}))) h3
        FROM t WHERE t.zone IS NULL
        UNION
        SELECT DISTINCT site, famille, attendu,
               h3_h3_to_string(unnest(h3_polygon_wkt_to_cells({box('z.ouest', 'z.sud', 'z.est', 'z.nord')}, {res}))) h3
        FROM t JOIN z ON z.nom = t.zone""")
    return c


def sweep(c) -> pd.DataFrame:
    """Detected fraction per site, version, mask and threshold set. A site observed without detection: 0."""
    h = c.execute("""SELECT tc.site, tc.famille, his.version, his.drap, his.wbin, his.fitbin, his.snrbin, sum(his.n) n
                     FROM his JOIN tc ON tc.h3 = his.h3 AND tc.famille = his.famille GROUP BY ALL""").df()
    v = c.execute("""SELECT tc.site, tc.famille, tc.attendu, cel.version, cel.drap, sum(cel.n) n
                     FROM cel JOIN tc USING (h3) GROUP BY ALL""").df()
    ng = c.execute("""SELECT tc.site, tc.famille, cel.version, count(DISTINCT cel.granule) n_gran
                      FROM cel JOIN tc USING (h3) GROUP BY ALL""").df()
    v = v.merge(ng, on=["site", "famille", "version"])
    rows = []
    for mask_name, bits in MASKS.items():
        hv = h[(h.drap.to_numpy(int) & bits) == 0]
        vv = v[(v.drap.to_numpy(int) & bits) == 0]
        total = v.groupby(["site", "famille", "attendu", "version"]).agg(n_tot=("n", "sum"), n_gran=("n_gran", "max"))
        valid = vv.groupby(["site", "famille", "attendu", "version"]).n.sum().reindex(total.index, fill_value=0)
        groups = dict(tuple(hv.groupby(["site", "famille", "version"])))
        for (site, fam, expected, ver), r in total.iterrows():
            g = groups.get((site, fam, ver), hv.iloc[:0])
            cube = np.zeros((len(WEIGHT_BINS), 20, len(SNR_BINS)))
            np.add.at(cube, (g.wbin.to_numpy(int), g.fitbin.to_numpy(int), g.snrbin.to_numpy(int)), g.n.to_numpy(float))
            cumulative = cube[::-1, ::-1, ::-1].cumsum(0).cumsum(1).cumsum(2)[::-1, ::-1, ::-1]     # ">= threshold"
            d = valid[(site, fam, expected, ver)]
            for wi, fi, si in itertools.product(range(len(WEIGHT_BINS)), range(14), range(len(SNR_BINS))):
                rows.append((site, fam, expected, ver, mask_name, WEIGHT_BINS[wi], FIT_BINS[fi], SNR_BINS[si],
                             cumulative[wi, fi, si] / d if d else np.nan, int(d), d / r.n_tot if r.n_tot else np.nan,
                             int(r.n_gran)))
    b = pd.DataFrame(rows, columns=["site", "famille", "attendu", "version", "masque", "w_min", "fit_min", "snr_min",
                                    "part", "pixels_valides", "part_valide", "granules"])
    b["groupe"] = np.where(b.famille.isin(GROUP_1_FAMILIES), 1, 2)
    return b


def tuned(b: pd.DataFrame, mask: str) -> pd.DataFrame:
    """Tuned method, for one mask."""
    b = b[(b.w_min == MIN_WEIGHT) & (b.masque == mask)]
    keys = ["version", "groupe", "masque", "w_min", "fit_min", "snr_min"]
    neg = b[b.attendu == "absent"].groupby(keys).part.max().rename("fausse_alarme_max")
    pos = b[b.attendu == "present"].groupby(keys).part.agg(detection_min="min", detection_med="median")
    s = pd.concat([neg, pos], axis=1).reset_index()
    chosen = []
    for (ver, grp), g in s.groupby(["version", "groupe"]):
        for level, max_false_alarm in LEVELS.items():
            ok = g[g.fausse_alarme_max.fillna(0) <= max_false_alarm]
            if ok.empty:
                continue
            m = ok.sort_values(["detection_min", "detection_med"], ascending=False).iloc[0]
            chosen.append({"methode": "reglee", "niveau": level, **m.to_dict()})
    return pd.DataFrame(chosen)


def statistical(b: pd.DataFrame, mask: str) -> pd.DataFrame:
    """Statistical method, for one mask."""
    rows = []
    for level, snr in STATISTICAL.items():
        d = b[(b.w_min == MIN_WEIGHT) & (b.masque == mask) & (b.fit_min == 0) & (b.snr_min == snr)]
        for (ver, grp), g in d.groupby(["version", "groupe"]):
            rows.append({"methode": "statistique", "niveau": level, "version": ver, "groupe": grp, "masque": mask,
                         "w_min": MIN_WEIGHT, "fit_min": 0.0, "snr_min": snr,
                         "fausse_alarme_max": g[g.attendu == "absent"].part.max(),
                         "detection_min": g[g.attendu == "present"].part.min(),
                         "detection_med": g[g.attendu == "present"].part.median()})
    return pd.DataFrame(rows)


def fractions_for(b, r) -> pd.DataFrame:
    """Rows of the sweep that match the threshold set `r`."""
    return b[(b.version == r.version) & (b.groupe == r.groupe) & (b.masque == r.masque) & (b.w_min == r.w_min)
             & (b.fit_min == r.fit_min) & (b.snr_min == r.snr_min)]


def leave_one_site_out(b: pd.DataFrame, mask: str) -> pd.DataFrame:
    """For each site: thresholds tuned without it, then the fraction obtained on it."""
    rows = []
    for site in b.site.unique():
        for r in tuned(b[b.site != site], mask).itertuples():
            for x in fractions_for(b[b.site == site], r).itertuples():
                rows.append({"site": site, "famille": x.famille, "attendu": x.attendu, "version": r.version,
                             "niveau": r.niveau, "part": x.part})
    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--counts", type=Path, default=CALIBRATION_DIR / "granules_r7b",
                   help="folder of the calibration counts (batch.py output)")
    p.add_argument("--resolution", type=int, default=7, help="H3 resolution of the counts (default: 7)")
    p.add_argument("--mask", default="spectf", choices=list(MASKS))
    args = p.parse_args()
    pd.set_option("display.width", 240)
    b = sweep(connect(args.counts, args.resolution))
    b.to_parquet(CALIBRATION_DIR / "balayage.parquet")

    no_threshold = (b.w_min == MIN_WEIGHT) & (b.fit_min == 0) & (b.snr_min == 0)
    print("Fraction of the pixels kept by each mask, per site:")
    print(b[no_threshold].pivot_table(index="site", columns=["version", "masque"], values="part_valide").round(3).to_string())
    print("\nDetection without any threshold (chosen mask):")
    print(b[no_threshold & (b.masque == args.mask)]
          .pivot_table(index=["site", "famille", "attendu"], columns="version", values="part").round(3).to_string())

    candidates = pd.concat([statistical(b, args.mask), tuned(b, args.mask)], ignore_index=True)
    print(f"\nThresholds (mask {args.mask}):")
    print(candidates.round(4).to_string(index=False))
    for method in ("statistique", "reglee"):
        parts = [fractions_for(b, r).assign(niveau=r.niveau) for r in candidates[candidates.methode == method].itertuples()]
        if parts:
            t = pd.concat(parts).pivot_table(index=["site", "famille", "attendu"], columns=["version", "niveau"], values="part")
            print(f"\nFractions on the reference sites, {method} method:")
            print(t.round(3).to_string())
    candidates.to_csv(CALIBRATION_DIR / "seuils_candidats.csv", index=False)
    loo = leave_one_site_out(b, args.mask)
    loo.to_csv(CALIBRATION_DIR / "validation_site_exclu.csv", index=False)
    print("\nTuned method, leave-one-site-out validation (fraction on the site when it was not used for tuning):")
    print(loo.pivot_table(index=["site", "famille", "attendu"], columns=["version", "niveau"], values="part").round(3).to_string())
    print(f"\nCandidates written to {CALIBRATION_DIR / 'seuils_candidats.csv'}; the thresholds used are in thresholds.py.")


if __name__ == "__main__":
    main()
