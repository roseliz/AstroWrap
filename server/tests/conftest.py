"""Fake data shared by the tests: an area of Mars and an Earth where one cell (the target) is identical to it.

Run from the repository root: python -m pytest server/tests
"""

import importlib
import sys
from pathlib import Path

import h3
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))       # repository root: the "server" package


def write(folder, module, table, body, df):
    d = folder / module
    d.mkdir(parents=True, exist_ok=True)
    df.assign(resolution=5, body=body).to_parquet(d / f"{table}_{body}_h3_5.parquet")


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """Mars area of 91 cells (footprint: 5 rings). On the Earth (disk of 15 rings):
    - target: its cell and its whole footprint identical to the area;
    - trap: an identical cell isolated among random values;
    - edge: at the edge of the data (half of its footprint is "at sea"), identical where there are data."""
    rng = np.random.default_rng(0)
    center = h3.latlng_to_cell(30, 10, 5)
    earth = list(h3.grid_disk(center, 15))
    mars = list(h3.grid_disk(h3.latlng_to_cell(-2, -6, 5), 5))
    n = len(earth)
    day, night = rng.uniform(250, 320, n), rng.uniform(200, 290, n)
    ring = sorted(h3.grid_ring(center, 6))
    target, trap, edge = ring[0], ring[len(ring) // 2], sorted(h3.grid_ring(center, 15))[0]
    pos = {c: i for i, c in enumerate(earth)}
    for c in list(h3.grid_disk(target, 5)) + list(h3.grid_disk(edge, 5)) + [trap]:
        if c in pos:
            day[pos[c]], night[pos[c]] = 280.0, 210.0
    write(tmp_path, "thermal_light_extrems", "thermal", "earth",
          pd.DataFrame({"h3": earth, "lst_day_mean": day, "lst_night_mean": night, "air_temperature_mean": day - 10,
                        "reliability": 1.0}))
    write(tmp_path, "thermal_light_extrems", "thermal", "mars",
          pd.DataFrame({"h3": mars, "lst_day_mean": 280.0, "lst_night_mean": 210.0, "reliability": 0.2}))
    monkeypatch.setenv("ANALOGUES_DATA", str(tmp_path))
    monkeypatch.setenv("ANALOGUES_CACHE", str(tmp_path / "cache"))
    import server.services.places as places                       # no network in the tests
    monkeypatch.setattr(places, "load_in_background", lambda: None)
    monkeypatch.setattr(places, "_layers", {"regions": None, "countries": None})
    monkeypatch.setattr(places, "nominatim", lambda lat, lon: None)
    # reload what keeps state or reads the settings at import: Earth in memory, cached references, app
    for name in ("server.core.config", "server.services.db", "server.services.earth", "server.services.combine",
                 "server.routes.meta", "server.routes.search", "server.main"):
        module = importlib.import_module(name)
        importlib.reload(module)
    main = sys.modules["server.main"]
    zone = [c for m in mars for c in h3.cell_to_children(m, 6)]
    yield main.app, zone, target, {"trap": trap, "edge": edge}
    # the app reads the Earth in a background thread: let it finish before the next test (or the end of Python)
    sys.modules["server.services.earth"]._ready.wait(60)
