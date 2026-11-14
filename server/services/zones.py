"""Reference area: H3 cells from the interface (resolution 6, compacted or not) -> resolution-5 cells."""

import h3
import numpy as np

from ..core import config


def to_resolution(cells: list):
    """(sorted resolution-5 cells, number of resolution-6 tiles of the area in each of them)."""
    res = config.RESOLUTION
    tiles = 0
    counts = {}
    for c in cells:
        if not h3.is_valid_cell(c):
            raise ValueError(f"invalid H3 cell: {c}")
        r = h3.get_resolution(c)
        tiles += 7 ** max(0, 6 - r)
        if tiles > config.MAX_ZONE_CELLS:
            raise ValueError(f"area too large: more than {config.MAX_ZONE_CELLS} tiles at resolution 6")
        if r <= res:
            for e in (h3.cell_to_children(c, res) if r < res else [c]):
                counts[e] = counts.get(e, 0.0) + 7.0 ** (6 - res)
        else:
            p = h3.cell_to_parent(c, res)
            counts[p] = counts.get(p, 0.0) + 7.0 ** max(0, 6 - r)
    if not counts:
        raise ValueError("empty area")
    keys = sorted(counts)
    return keys, np.array([counts[c] for c in keys])

