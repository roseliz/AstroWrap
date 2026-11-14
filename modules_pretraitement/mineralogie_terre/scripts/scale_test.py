"""Scale test: effect of coarser pixels (300 m, ~1 km) on the detected fraction, in sensor geometry.

Linear mixing model: the band depth of a block is the mean of its pixels' band depths (0 where the family is
not detected); the noise of the block is the median uncertainty of one pixel (same signal-to-noise ratio per
pixel as the fine instrument: a cautious assumption). A block is detected when depth / noise >= 3 (medium).

Reads one v002 granule of each of 5 calibration zones (~0.7 GB in total, deleted after use). Needs the
calibration list (run.py calibration-list).

  python scale_test.py [download folder]
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from batch import HttpsSource
from families import FAMILIES, weight_matrix
from granule import MASKS, read_granule
from utils import CALIBRATION_DIR, earthdata_login

ZONES = ["white_sands", "cuprite", "wadi_rum", "pilbara", "meteor_crater"]
BLOCKS = {"300 m": 5, "1 km": 17}                 # block side in 60 m pixels


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("folder", nargs="?", type=Path, help="download folder (default: a temporary folder)")
    args = p.parse_args()
    folder = args.folder or Path(tempfile.mkdtemp(prefix="emit_scale_"))
    folder.mkdir(parents=True, exist_ok=True)
    source = HttpsSource(earthdata_login())
    granules = pd.read_parquet(CALIBRATION_DIR / "liste.parquet")
    W = weight_matrix()
    invalid_bits = MASKS["spectf"]
    rows = []
    for zone in ZONES:
        g = granules[(granules.zone == zone) & (granules.version == "002")].iloc[0]
        paths = []
        for url in (g.url_min, g.url_unc, g.url_masque):
            path = folder / url.rsplit("/", 1)[-1]
            if not path.exists():
                source.download(url, path)
            paths.append(path)
        d = read_granule(*paths)
        valid = ((d["drap"].astype(int) & invalid_bits) == 0) & (d["id1"] != -9999) & (d["id2"] != -9999)
        for k, f in enumerate(FAMILIES):
            group = 1 if f == "oxyde_fer" else 2
            ids = np.clip(d[f"id{group}"].astype(int), 0, W.shape[0] - 1)
            w, bd, unc = W[ids, k], d[f"bd{group}"], d[f"unc{group}"]
            snr = np.where(unc > 0, bd / np.where(unc > 0, unc, 1), 0)
            detected = valid & (w >= 0.1) & (snr >= 3) & (ids > 0)
            bd_detected = np.where(detected, bd, 0.0)
            median_unc = np.nanmedian(np.where(valid & (unc > 0), unc, np.nan))
            row = {"zone": zone, "family": f, "60 m": detected[valid].mean()}
            for name, b in BLOCKS.items():
                ny, nx = (detected.shape[0] // b) * b, (detected.shape[1] // b) * b
                V = valid[:ny, :nx].reshape(ny // b, b, nx // b, b).mean((1, 3))
                B = bd_detected[:ny, :nx].reshape(ny // b, b, nx // b, b).sum((1, 3)) / (b * b)
                ok = V >= 0.5                                  # block at least half valid
                row[name] = ((B / median_unc >= 3) & ok).sum() / ok.sum()
            rows.append(row)
        for path in paths:
            path.unlink(missing_ok=True)
    t = pd.DataFrame(rows)
    t = t[t["60 m"] >= 0.01]
    for name in BLOCKS:
        t[f"ratio {name}"] = t[name] / t["60 m"]
    pd.set_option("display.width", 200)
    print(t.round(3).to_string(index=False))
    print("\nMedian ratio (coarse detected fraction / 60 m):",
          t[[f"ratio {name}" for name in BLOCKS]].median().round(2).to_dict())


if __name__ == "__main__":
    main()
