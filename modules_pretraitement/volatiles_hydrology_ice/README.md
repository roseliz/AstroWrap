# Volatiles, hydrology, ice and permafrost

Surface ice, ground ice, soil water, open water and permanent shadows for every H3 cell (resolution 5) of the Earth,
Mars and the Moon. In the app it is the **Ice and water** criterion.

The three bodies don't measure water the same way (permafrost models and soil moisture on Earth, neutrons and radar on
Mars and the Moon). So each column holds a quantity that reads the same everywhere (share, 0–1 index, depth in m,
mass %), plus a **within-body rank** for soil water.

| Value | Means |
|---|---|
| `NaN` | Unknown |
| `0` | Absent, or impossible on that body (no surface liquid water on Mars or the Moon, no permanent shadow on Earth or Mars) |

## Quick start

From the repository root:

```bash
pip install -r modules_pretraitement/volatiles_hydrology_ice/requirements.txt
python modules_pretraitement/volatiles_hydrology_ice/scripts/pretraitement.py --corps mars
```

| Command | Time |
|---|---|
| `--corps mars` | ~5 min, 213 MB on first run |
| `--corps moon` | ~1 min once Diviner (1.2 GB) is downloaded |
| `--corps earth` | mostly the JRC download (up to ~16 GB, tile by tile, deleted as it goes) |
| no `--corps` | the three |
| `--corps earth --glace-seulement` | ~1 min: adds RGI glaciers to an existing Earth output |

## Columns

Every table starts with `body`, `resolution`, `h3`.

| Column | Earth | Mars | Moon |
|---|---|---|---|
| `part_glace_surface` (0–1) | Glaciers (RGI 7.0) or ice sheets (Natural Earth, minus ice-free Antarctica), the larger | 1 if surface water ice > 1 kg/m² every month (caps, MCD), else 0 | M3 exposed-ice area / cell area, south of 75° S; empty elsewhere |
| `indice_glace_sol` (0–1) | Permafrost fraction (ESA CCI); 0 where none, or where mean air > +3 °C | Best positive SWIM ice consistency, 0 to > 5 m; 0 if none | Share of area with ice stable from the surface to 2.87 m (Diviner), poleward of 80° |
| `profondeur_glace_m` | Active layer thickness | Shallowest slice with consistency ≥ 0.25: 0.5, 3 or 5 m | Mean depth of stable ice, 0 to 2.87 m |
| `eau_sol_pct` (mass %) | **Estimate**: volumetric moisture × 100 / 1.4 g/cm³ | Odyssey GRS H₂O, top meter | Lunar Prospector hydrogen × 8.94 |
| `eau_sol_rang` (0–1) | Rank of `eau_sol_pct` in the body | same | same |
| `humidite_sol` (m³/m³) | Mean soil moisture (ESA CCI SM) | empty | empty |
| `part_eau_libre` (0–1) | Share of land pixels flooded > half the time (JRC) | 0 | 0 |
| `part_ombre_permanente` (0–1) | 0 | 0 | Share in permanent shadow (LOLA); 0 equatorward of 65° |
| `couverture`, `fiabilite` | Share available of `part_glace_surface`, `indice_glace_sol`, `eau_sol_pct`, `part_eau_libre` | same | Of `indice_glace_sol`, `eau_sol_pct`, `part_ombre_permanente` |

`profondeur_glace_m`, `humidite_sol` and `eau_sol_rang` don't count toward `couverture`. `fiabilite` = `couverture` for now.

Output: `pretreatment_data/volatiles_hydrology_ice/volatiles_hydrology_ice_<body>_h3_5.parquet`, plus `<body>.duckdb`.

## Sources

| Body | Source | For | How |
|---|---|---|---|
| Earth | ESA CCI Permafrost v5.0, `PFR` and `ALT`, 1 km, 2021–2023, 25–85° N and ice-free Antarctica | `indice_glace_sol`, `profondeur_glace_m` | Automatic, CEDA, no account |
| Earth | RGI 7.0 (NSIDC-0770), glacier outlines | `part_glace_surface` | Automatic with Earthdata (~1 GB); or zips in `inputs/volatiles_hydrology_ice/rgi/` |
| Earth | Natural Earth 1:10 m land and glaciated areas | Land cells, Greenland and Antarctic ice sheets | Automatic, ~12 MB |
| Earth | JRC Global Surface Water v1.4, 30 m, 60° S–80° N | `part_eau_libre` | Automatic, up to ~16 GB (`--sans-jrc` skips it) |
| Earth | ESA CCI Soil Moisture COMBINED v09.2, 0.25°, daily | `humidite_sol`, `eau_sol_pct` | Automatic, 1 day in 7 of 2022 (~52 × 2.5 MB) |
| Mars | SWIM 2.0 (Putzig et al., PSI), 0–1, 1–5, > 5 m, 3 km, ±60°, below +1 km | `indice_glace_sol`, `profondeur_glace_m` | Automatic, 3 × 71 MB, resumes dropped connections |
| Mars | Odyssey GRS H₂O mass %, 5° bins (PDS) | `eau_sol_pct` | Automatic, 60 KB |
| Mars | Mars Climate Database v6.2, surface water ice | `part_glace_surface` | **Manual**, `inputs/mcd/`; never redistribute; without it the column is empty |
| Moon | Diviner Polar Resource Product (Paige et al. 2010), poleward of 80° | `indice_glace_sol`, `profondeur_glace_m` | Automatic, 2 × 605 MB, kept in `cache/` |
| Moon | Lunar Prospector hydrogen ppm, 0.5° (Feldman et al. 2001) | `eau_sol_pct` | Automatic, 14 MB |
| Moon | Lemelin et al. 2021 (Zenodo 4646092, CC BY 4.0): 169 south polar shadowed regions with M3 ice (Li et al. 2018) | `part_glace_surface` | Automatic, 0.5 MB |
| Moon | LOLA permanent shadow maps, 240 m, 65–90° (Mazarico et al. 2011) | `part_ombre_permanente` | Automatic, 2 × 0.6 MB |

Not used: **LEND** neutrons (no ready global map in the PDS), and **M3 ice at the North Pole** (no published table).

### Earthdata, for RGI only (optional)

| Order | Where the credentials are read |
|---|---|
| 1 | `EARTHDATA_USERNAME`, `EARTHDATA_PASSWORD` in the environment or the root `.env` (`USERNAME_EARTHACCESS`, `PASSWORD_EARTHACCESS` also work) |
| 2 | `~/.netrc` |
| 3 | Interactive terminal: asks at the keyboard (Ctrl+C to go on without RGI). In the background, never blocks: Natural Earth only, logged |

RGI 7.0 has no granules in NASA's CMR, so the module browses the
[NSIDC folder](https://daacdata.apps.nsidc.org/pub/DATASETS/nsidc0770_rgi_v7/) for `RGI2000-v7.0-G-*.zip`.
On HTTP 403, authorize **NSIDC_DATAPOOL_OPS** in the Earthdata profile, or download the zips by hand.

## Options

| Option | Effect |
|---|---|
| `--corps earth mars moon` | Bodies (default: all three) |
| `--resolution 5` | H3 resolution |
| `--zone W S E N` | Only this box (tests); Mars and Moon files still download in full |
| `--sans-jrc` | Earth: no JRC, `part_eau_libre` empty |
| `--sans-rgi` | Earth: Natural Earth glaciers only |
| `--glace-seulement` | Earth: only recompute `part_glace_surface` |
| `--rgi /path` | Earth: RGI 7.0 folder |
| `--annee-humidite 2022`, `--pas-jours 7` | Earth: soil moisture year, one day in N |
| `--annees-permafrost 2021 2022 2023` | Earth: permafrost years |
| `--mcd /path` | Mars: MCD folder |

## Method

| Topic | Rule |
|---|---|
| Cells | Mars, Moon: all 2,016,842. Earth: cells holding the center of a 0.05° Natural Earth land pixel |
| Fine grids (CCI 1 km, SWIM 3 km, JRC 30 m, LOLA 240 m, Diviner) | Pixels grouped in blocks, each block to the cell of its center, mean of valid blocks. Mars: a cell with no block takes the block holding its center |
| Coarse grids (soil moisture, GRS, Lunar Prospector, MCD) | Value at the cell center |
| Earth surface ice | Max of RGI (peripheral glaciers: < 1 km² to the centroid cell, larger via res-8 sub-cells) and Natural Earth (ice sheets) |
| Antarctica | Ice-free ground removed using CCI Permafrost (5 km blocks ≥ 90% ice-free, ~48,000 km²): keeps the Dry Valleys, drops isolated nunataks |
| Permafrost | Mean 2021–2023. Empty cells become 0 north of 25° N or where mean air > +3 °C (Sahara, Amazon…), else stay empty (high Andes, under ice sheets) |
| Mars ground ice (SWIM) | Consistency −1 to +1; index = best positive slice. Depth only where ≥ 0.25 (0.06 at Gale gives no depth; 0.5 lost the 0–1 m slice at Arcadia, where craters show ice a few dm down) |
| Moon ground ice (Diviner) | `ice_depth`: 0 stable at surface, −999 not stable within 2.87 m, −1 (cold traps, ~77 K) read as 0. A cell needs ≥ 50% mesh cover |
| Soil water | Mars: water-equivalent hydrogen, top meter (includes hydrated minerals). Moon: hydrogen × 8.94, negatives clamped to 0. Earth: top few cm only, so only `eau_sol_rang` compares |
| Permanent shadows | LOLA polar stereographic, 4 × 4 blocks (~1 km). Checked on Shackleton, Faustini, Haworth; totals 25,564 km² north, 28,642 km² south match the source |
| Open water | JRC occurrence ≥ 50%; ocean masked; no tiles beyond 80° N and 60° S, so empty there |

## Limits

| Limit | Effect |
|---|---|
| `indice_glace_sol` | Mixes a permafrost fraction (Earth), a consistency index (Mars) and a stable area (Moon): compare with care |
| Mars caps | MCD grid 3.75° × 5.6°: caps show as 220 km blocks |
| Cell means | A glacier or permafrost share doesn't say where in the cell the ice is |
| Moon surface ice | South Pole only, ~1% of a cell at most; region counts spread by area; left out of `couverture` |
| SWIM gaps | Nothing beyond ±60° or above +1 km, even where ice is certain (Phoenix, 68° N) |
| Mountain permafrost | Missing in the Andes, New Zealand, East Africa |
| Uncertainties | Not in the tables |

## Files

| Path | Content |
|---|---|
| `scripts/pretraitement.py` | Entry point, three bodies |
| `requirements.txt` | Dependencies |
| `inputs/volatiles_hydrology_ice/rgi/` | RGI zips, if downloaded by hand |
| `inputs/mcd/` | Mars Climate Database, by hand, never committed |
