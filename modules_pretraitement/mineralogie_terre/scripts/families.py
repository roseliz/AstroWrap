"""The 10 validated EMIT minerals grouped into 6 families, and the weight of each family per library entry.

Source: the official EMIT mineral grouping matrix (repository emit-sds/emit-sds-l2b,
data/mineral_grouping_matrix_20230503.csv, Apache 2.0). It is downloaded once from a pinned commit into the
module cache, and its SHA-256 is checked. For each entry of the spectral library (the `Index` given by
group_1_mineral_id and group_2_mineral_id), it gives the fraction of each of the 10 minerals in the
reference sample. The weight of a family is the sum of the fractions of its minerals.

EMIT L2B v002 adds 18 library entries (295 to 312, from mineral_id_matrix_v6.00a6.csv) that are missing
from the 2023 matrix: they are completed in V002_ADDITIONS below.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from utils import CACHE_DIR

GROUPING_MATRIX_NAME = "mineral_grouping_matrix_20230503.csv"
GROUPING_MATRIX_COMMIT = "fba601868fe630f4e119b71175558ed39dbe49aa"     # last upstream change, 2023-05-18
GROUPING_MATRIX_URL = (f"https://raw.githubusercontent.com/emit-sds/emit-sds-l2b/{GROUPING_MATRIX_COMMIT}/"
                       f"data/{GROUPING_MATRIX_NAME}")
GROUPING_MATRIX_SHA256 = "582f3c1d4dc670d90ccfa0dbffa6710d6ffbd0d38df6b6a772219c7ee4350a73"
GROUPING_MATRIX = CACHE_DIR / "emit_sds_l2b" / GROUPING_MATRIX_NAME

FAMILIES = ["oxyde_fer", "argile_al", "argile_fe_mg", "mica", "carbonate", "sulfate"]
MINERALS = {
    "oxyde_fer": ["Hematite", "Goethite"],           # iron oxides
    "argile_al": ["Kaolinite", "Montmorillonite"],   # Al clays
    "argile_fe_mg": ["Chlorite", "Vermiculite"],     # Fe/Mg clays
    "mica": ["Illite+Muscovite"],
    "carbonate": ["Calcite", "Dolomite"],
    "sulfate": ["Gypsum"],
}
ALL_MINERALS = [m for f in FAMILIES for m in MINERALS[f]]

# Library entries 295 to 312 of v002 (mineral_id_matrix_v6.00a6.csv), missing from the official grouping
# matrix (2023). Fractions deduced from the USGS sample name; minerals not listed = 0.
# Jarosites (304-311) and bloedite (312) are not among the 10 validated minerals: zero weight.
# (index, Tetracorder group, USGS sample name, {mineral: fraction})
V002_ADDITIONS = [
    (295, 1, "Hematite-nano_KP58610 400nm", {"Hematite": 1.0}),
    (296, 1, "Hematite-n0.03_KP58610+Qtz", {"Hematite": 0.03}),
    (297, 1, "Goethite-nano_KP943 70nm", {"Goethite": 1.0}),
    (298, 1, "Goethite-n0.50_KP943+Qtz", {"Goethite": 0.5}),
    (299, 1, "Hematite.10+Goethite.90 hg1", {"Hematite": 0.1, "Goethite": 0.9}),
    (300, 1, "Hematite.20 Goethite.80 hg2", {"Hematite": 0.2, "Goethite": 0.8}),
    (301, 1, "Hematite.30 Goethite.70 hg3", {"Hematite": 0.3, "Goethite": 0.7}),
    (302, 1, "Hematite0.1+Goeth0.4+Qtz.5", {"Hematite": 0.1, "Goethite": 0.4}),
    (303, 1, "Hematite0.4+Goeth0.1+Qtz.5", {"Hematite": 0.4, "Goethite": 0.1}),
    (304, 1, "Ammonio-Jarosite SCR-NHJ", {}),
    (305, 1, "Jarosite GDS100 Na Sy 90C", {}),
    (306, 1, "Jarosite GDS101 Na Sy 200C", {}),
    (307, 1, "Jarosite GDS98 K 90C Syn", {}),
    (308, 1, "Jarosite JR2501 (K)", {}),
    (309, 1, "Jarosite NMNH95074-1 (Na)", {}),
    (310, 1, "Jarosite SJ-1 H3O 10-20%", {}),
    (311, 1, "Jarosite_Thin_Film GDS243", {}),
    (312, 2, "Bloedite GDS147", {}),
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def grouping_matrix(path: Path = GROUPING_MATRIX) -> Path:
    """Path of the official grouping matrix, downloaded from the pinned commit on first use and checked."""
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".part")
        try:
            print(f"Downloading the EMIT grouping matrix ({GROUPING_MATRIX_COMMIT[:7]})...", flush=True)
            urllib.request.urlretrieve(GROUPING_MATRIX_URL, partial)
        except OSError as e:
            partial.unlink(missing_ok=True)
            sys.exit(f"EMIT grouping matrix: download failed ({e}). Download {GROUPING_MATRIX_URL} "
                     f"manually and save it as {path}")
        partial.replace(path)
    if _sha256(path) != GROUPING_MATRIX_SHA256:
        path.unlink()
        sys.exit(f"EMIT grouping matrix: unexpected content (SHA-256 mismatch), {path} deleted; run again")
    return path


def weight_table() -> pd.DataFrame:
    """One row per library entry: index, groupe (1 or 2), nom, weight of each family (0 to 1)."""
    m = pd.read_csv(grouping_matrix())
    m[ALL_MINERALS] = m[ALL_MINERALS].fillna(0.0)
    official = m[["Index", "Group", "Name", *ALL_MINERALS]].rename(
        columns={"Index": "index", "Group": "groupe", "Name": "nom"})
    additions = pd.DataFrame([{"index": i, "groupe": g, "nom": name, **{k: fractions.get(k, 0.0) for k in ALL_MINERALS}}
                              for i, g, name, fractions in V002_ADDITIONS])
    t = pd.concat([official, additions], ignore_index=True)
    for f in FAMILIES:
        t[f] = t[MINERALS[f]].sum(axis=1).clip(0, 1)
    if t["index"].duplicated().any():
        raise ValueError("duplicate index in the family weight table")
    return t[["index", "groupe", "nom", *FAMILIES]]


def weight_matrix() -> np.ndarray:
    """weights[index, k] for the family FAMILIES[k] (index 0 = no mineral)."""
    t = weight_table()
    w = np.zeros((int(t["index"].max()) + 1, len(FAMILIES)), dtype=np.float32)
    w[t["index"].to_numpy()] = t[FAMILIES].to_numpy(np.float32)
    return w
