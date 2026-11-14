"""Granule list for an AWS run.

Pilot: 3 granules already processed locally (to compare the results) + N granules drawn at random from the
worldwide selection (to measure throughput and cost). Full: the whole selection (selection.py output).

  python make_list.py [--n 30]   ->  lists/pilot.parquet
  python make_list.py --full     ->  lists/full.parquet
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                                    # repository root
CACHE_DIR = ROOT / "cache" / "mineralogie_terre"
LISTS_DIR = HERE / "lists"
LOCAL_REFERENCES = ["EMIT_L2B_MIN_002_20220902T060456", "EMIT_L2B_MIN_002_20240727T213005",
                    "EMIT_L2B_MIN_002_20241020T183829"]
COLUMNS = ["granule", "version", "url_min", "url_unc", "url_masque"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--n", type=int, default=30, help="random granules in the pilot list (default: 30)")
    p.add_argument("--full", action="store_true", help="the whole selection instead of a pilot")
    args = p.parse_args()
    selection = pd.read_parquet(CACHE_DIR / "catalogue" / "selection.parquet")
    LISTS_DIR.mkdir(exist_ok=True)
    if args.full:
        t, name = selection[COLUMNS], "full"
    else:
        calibration = pd.read_parquet(CACHE_DIR / "calibration" / "liste.parquet")
        local = calibration[calibration.granule.isin(LOCAL_REFERENCES)][COLUMNS]
        drawn = selection[~selection.granule.isin(LOCAL_REFERENCES)].sample(args.n, random_state=1)[COLUMNS]
        t, name = pd.concat([local, drawn]), "pilot"
    t = t.drop_duplicates("granule").reset_index(drop=True)
    output = LISTS_DIR / f"{name}.parquet"
    t.to_parquet(output, index=False)
    print(f"{len(t)} granules -> {output}")


if __name__ == "__main__":
    main()
