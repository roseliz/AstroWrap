"""Detection thresholds, frozen in phase 1 (2026-11-13). EMIT L2B MIN v002 only.

A valid pixel is geolocated and has no SpecTf-Cloud, cirrus, water or spacecraft flag (EMIT L2A mask v003).
A family is detected on a pixel when a library entry containing at least 10 % of it (min_weight) is
identified with band depth / uncertainty >= min_snr. The statistical thresholds were fixed in advance
(2, 3 and 5 times the uncertainty), identical for both Tetracorder groups, and checked on the reference
sites of sites.CALIBRATION_SITES and on the independent ones of sites.AUDIT_SITES.
"""

from __future__ import annotations

import pandas as pd

# level, EMIT version, min_weight, min_fit, min_snr, mask (granule.MASKS)
DETECTION_THRESHOLDS = [
    ("faible", "002", 0.1, 0.0, 2.0, "spectf"),   # weak
    ("moyen", "002", 0.1, 0.0, 3.0, "spectf"),    # medium
    ("fort", "002", 0.1, 0.0, 5.0, "spectf"),     # strong
]
LEVELS = [level for level, *_ in DETECTION_THRESHOLDS]


def thresholds_table() -> pd.DataFrame:
    """DETECTION_THRESHOLDS as a table (columns kept from the original seuils.csv)."""
    return pd.DataFrame(DETECTION_THRESHOLDS, columns=["niveau", "version", "poids_min", "fit_min", "snr_min", "masque"])
