# Volatiles, Hydrology, Ice, and Permafrost

Surface ice, ground ice, soil water, open water, and permanent shadows per H3 cell (resolution 5), for **Earth, Mars, and the Moon**. All three bodies share the exact same columns. An empty column (`NaN`) means "unknown"; it equals 0 when the phenomenon does not exist on that body (no stable liquid water on the surface of Mars or the Moon, no permanent shadows on Earth or Mars).

The three bodies do not measure ice and water in the same way: Earth relies on permafrost models and soil moisture data, while Mars and the Moon rely on neutron and radar measurements. For each column, the feature vector therefore provides a quantity that reads identically everywhere (a fraction from 0 to 1, an index from 0 to 1, a depth in meters, a mass percentage) and, for soil water, a **within-body rank**.

## Files

```
run.sh                        entry point (./pipeline run volatiles_hydrology_ice)
requirements.txt              module dependencies
inputs.txt                    optional manually copied inputs: MCD (Mars), RGI 7.0 (Earth)
audit.csv                     physical bounds and reference sites (./pipeline audit volatiles_hydrology_ice)
scripts/pretraitement.py      preprocessing script for all three bodies
```

## Sources and Setup

| Body | Source | Used for | How to obtain |
|---|---|---|---|
| Earth | **ESA CCI Permafrost** v5.0: `PFR` (permafrost fraction) and `ALT` (active layer thickness), 1 km, 2021 to 2023, Northern Hemisphere (25° to 85° N) and ice-free Antarctica | `indice_glace_sol`, `profondeur_glace_m` | automatic, CEDA without account; 3 × (12 + 31 MB) in the north, ~1 MB per file in the south |
| Earth | **RGI 7.0** (NSIDC-0770, glacier outlines) | `part_glace_surface` | automatic with an Earthdata account (~1 GB); without an account, or with `--sans-rgi`, Natural Earth only. Alternatively, place the zip files in `inputs/volatiles_hydrology_ice/rgi/` |
| Earth | **Natural Earth** 1:10 m, land and glaciated areas (public domain) | land cells, Greenland and Antarctic ice sheets (which RGI lacks) | automatic (~12 MB) |
| Earth | **JRC Global Surface Water** v1.4 (water occurrence, 30 m, 60° S to 80° N) | `part_eau_libre` | automatic, one 10° tile at a time, read then deleted; **up to ~16 GB transferred** (`--sans-jrc` to skip) |
| Earth | **ESA CCI Soil Moisture** COMBINED v09.2 (0.25°, daily) | `humidite_sol`, `eau_sol_pct` | automatic, CEDA; 1 day every 7 days in 2022 (~52 files of 2.5 MB) |
| Mars | **SWIM 2.0** (Putzig et al., Planetary Science Institute): consistency with subsurface ice at 0–1 m, 1–5 m, and > 5 m, 3 km, ± 60°, below +1 km | `indice_glace_sol`, `profondeur_glace_m` | automatic (3 × 71 MB); the server drops connections, the module resumes them automatically |
| Mars | **Odyssey GRS**, water ($\text{H}_2\text{O}$) in mass %, 5° bins smoothed over 10° (PDS, ODY-M-GRS-5-ELEMENTS-V1.0) | `eau_sol_pct` | automatic (60 KB) |
| Mars | **Mars Climate Database v6.2** (LMD), surface water ice | `part_glace_surface` | **manual, already done**: `inputs/mcd/`. Do not redistribute. Without it, the column remains empty |
| Moon | **Diviner Polar Resource Product** (Paige et al. 2010, PDS): stable ice depth, 2.88-million-triangle mesh per pole, poleward of 80° | `indice_glace_sol`, `profondeur_glace_m` | automatic (2 × 605 MB, kept in `cache/`) |
| Moon | **Lunar Prospector**, hydrogen in mass ppm, 0.5° bins (Feldman et al. 2001, PDS) | `eau_sol_pct` | automatic (14 MB) |
| Moon | **Lemelin et al. 2021** (Zenodo 4646092, CC BY 4.0): the 169 south polar permanently shadowed regions where **M3** detected exposed ice (Li et al. 2018), with the count of 280 m pixels | `part_glace_surface` | automatic (0.5 MB) |
| Moon | **LOLA**, permanent shadow maps at 240 m, 65° to 90° (Mazarico et al. 2011, PGDA/Goddard) | `part_ombre_permanente` | automatic (2 × 0.6 MB) |

Excluded planned source: **LEND** neutrons (no ready-to-read global map in the PDS: published maps are only in papers). **Surface ice observed by M3** is only available as open data for the South Pole (Lemelin et al. 2021); North Pole detections (Li et al. 2018) do not have a published numerical table.

**NASA Earthdata credentials (RGI only, optional).** The module looks for credentials in this order: the `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD` environment variables, or the same lines in the `.env` file at the repository root (ignored by git; `USERNAME_EARTHACCESS` and `PASSWORD_EARTHACCESS` also work), then `~/.netrc` (`./setup.sh`). If none are found and the program runs in an interactive terminal, it **prompts for the username and password via keyboard** (Ctrl+C to continue without RGI); inside a detached `tmux` session or in the background, it never blocks and falls back to Natural Earth, logging this in the console log and Parquet metadata.

RGI 7.0 (NSIDC-0770) has no granules indexed in NASA's CMR catalog (`earthaccess.search_data` returns 0): the module therefore browses https://daacdata.apps.nsidc.org/pub/DATASETS/nsidc0770_rgi_v7/ using the Earthdata session and downloads the `RGI2000-v7.0-G-*.zip` archives (glacier outlines by region). If the server returns 403, authorize the "NSIDC_DATAPOOL_OPS" application in your Earthdata profile (Applications > Authorized Apps), or manually download the zip files into `inputs/volatiles_hydrology_ice/rgi/`.

To add RGI to an already computed Earth output without re-running JRC, soil moisture, or permafrost:
`./pipeline run volatiles_hydrology_ice --corps earth --glace-seulement` (takes one minute, ~1 GB for RGI).

## Running

```bash
./pipeline check volatiles_hydrology_ice
./pipeline run volatiles_hydrology_ice --corps mars          # ~5 min, 213 MB on first run
./pipeline run volatiles_hydrology_ice --corps moon          # ~1 min once the 1.2 GB of Diviner data is downloaded
./pipeline run volatiles_hydrology_ice --corps earth         # mostly JRC download time
./pipeline run volatiles_hydrology_ice                       # all three bodies
./pipeline audit volatiles_hydrology_ice
./pipeline publish volatiles_hydrology_ice
```

| Option | Effect |
|---|---|
| `--corps earth mars moon` | bodies to process (default: all three) |
| `--resolution 5` | H3 resolution |
| `--zone W S E N` | restrict computation to a bounding box (testing); Mars and Moon files are still downloaded in full |
| `--sans-jrc` | Earth: skip JRC (`part_eau_libre` left empty) |
| `--sans-rgi` | Earth: use Natural Earth glaciers only |
| `--glace-seulement` | Earth: recompute only `part_glace_surface` in the existing output (RGI) |
| `--rgi /path` | Earth: directory containing RGI 7.0 files |
| `--annee-humidite 2022`, `--pas-jours 7` | Earth: soil moisture year and sampling step (1 day every N days) |
| `--annees-permafrost 2021 2022 2023` | Earth: permafrost years (2021 to 2023 in v5.0) |
| `--mcd /path` | Mars: MCD directory (default: `inputs/mcd`) |

Outputs are saved in `pretreatment_data/volatiles_hydrology_ice/`:
`volatiles_hydrology_ice_{earth,mars,moon}_h3_5.parquet` and `{earth,mars,moon}.duckdb`.

## Columns

`body`, `resolution`, `h3`, followed by:

| Column | Earth | Mars | Moon |
|---|---|---|---|
| `part_glace_surface` (0-1) | fraction of the cell covered by glaciers (RGI 7.0) or continental ice (Natural Earth, minus ice-free Antarctic ground), whichever is larger | 1 if surface water ice exceeds $1\text{ kg/m}^2$ in all months (polar caps, MCD), otherwise 0 | area of M3 exposed-ice pixels / cell area (South Pole, poleward of 75° S: 0 if M3 detected nothing); empty elsewhere |
| `indice_glace_sol` (0-1) | permafrost fraction (ESA CCI), 0 = none (also where mean air temperature exceeds $+3\ ^\circ\text{C}$) | highest positive ice consistency between 0 and $> 5\text{ m}$ (SWIM), 0 = inconsistent | fraction of area where water ice is stable from the surface down to 2.87 m (Diviner), poleward of 80° |
| `profondeur_glace_m` | active layer thickness, i.e., depth to the permafrost table | shallowest depth slice with consistency $\ge 0.25$: 0.5 m, 3 m, or 5 m ("$> 5\text{ m}$"), averaged over those pixels; empty if the cell index is below 0.25 | mean depth of stable ice (0 to 2.87 m), where present |
| `eau_sol_pct` (mass %) | **estimate**: volumetric soil moisture $\times 100 / 1.4\text{ g/cm}^3$ | Odyssey GRS $\text{H}_2\text{O}$, top meter | Lunar Prospector hydrogen $\times 8.94$ |
| `eau_sol_rang` (0-1) | rank of `eau_sol_pct` among cells of the same body | same | same |
| `humidite_sol` ($\text{m}^3/\text{m}^3$) | mean volumetric soil moisture (ESA CCI SM) | empty | empty |
| `part_eau_libre` (0-1) | fraction of land pixels inundated more than half the time (JRC) | 0 | 0 |
| `part_ombre_permanente` (0-1) | 0 | 0 | fraction of the cell in permanent shadow (LOLA), 0 equatorward of 65° |
| `couverture`, `fiabilite` | fraction of available indicators among `part_glace_surface`, `indice_glace_sol`, `eau_sol_pct`, `part_eau_libre`; `fiabilite` = `couverture` (provisional, same rule as other modules) | same | among `indice_glace_sol`, `eau_sol_pct`, `part_ombre_permanente` (excludes `part_glace_surface`, which is missing in the north) |

`profondeur_glace_m` is only populated where ice is present (active layer: where permafrost exists); it does not count toward `couverture`, nor do `humidite_sol` and `eau_sol_rang`, which are derived from `eau_sol_pct`.

## Method

- **Cells.** Mars and Moon: all 2,016,842 cells. Earth: cells containing the center of at least one 0.05° land pixel from Natural Earth. An H3 resolution 5 cell is ~250 $\text{km}^2$ on Earth, ~72 $\text{km}^2$ on Mars, and ~19 $\text{km}^2$ on the Moon (cells share identical latitude and longitude coordinates).
- **Fine grids** (CCI Permafrost 1 km, SWIM 3 km, JRC 30 m, LOLA 240 m, Diviner triangles of ~0.1 $\text{km}^2$): pixels are first aggregated into blocks, then each block is assigned to the cell containing its center; the cell value is the mean of valid blocks. On Mars, where a block (6 km) is close in size to a cell (9 km), any cell without a block takes the block containing its center. **Coarse grids** (soil moisture 0.25°, GRS 5°, Lunar Prospector 0.5°, MCD): value of the grid cell containing the H3 cell center.
- **Surface ice on Earth.** RGI 7.0 excludes ice sheets (only peripheral glaciers are included): `part_glace_surface` takes the maximum of the RGI fraction and the Natural Earth fraction. An RGI glacier smaller than 1 $\text{km}^2$ is assigned to the cell containing its centroid, while larger ones are rasterized via H3 resolution 8 sub-cells. Natural Earth covers all of Antarctica, including the McMurdo Dry Valleys: south of 60° S, each 0.05° pixel has its ice-free ground fraction subtracted using ESA CCI Permafrost (domain AREA27, which only has values over ice-free ground; 5 km blocks, averaged across years). This raw mask covers ~183,500 $\text{km}^2$, 4 to 8 times larger than rock outcrop inventories (21,745 $\text{km}^2$, Burton-Johnson et al. 2016), because any 1 km pixel touching rock counts in full. Only 5 km blocks that are at least 90% ice-free remove ice: ~48,000 $\text{km}^2$ in total, capturing the full Dry Valleys while excluding isolated nunataks. Without these files, the entire continent remains classified as ice.
- **Permafrost.** The three years 2021 to 2023 are averaged (over valid pixels). ESA CCI Permafrost only models ice-free ground, and only where permafrost is plausible: Ulaanbaatar has a value of 0, whereas Montreal or Moscow are empty. An empty cell not covered by continental ice is therefore assigned 0 (`zero_hors_pergelisol`): north of 25° N, and anywhere mean annual air temperature exceeds $+3\ ^\circ\text{C}$ (`air_temperature_mean` from the `thermal_light_extrems` module, MERRA-2, read if already computed), such as the Sahara, Australia, or the Amazon. Elsewhere (cold cells outside the CCI domain: high Andes, beneath ice sheets), `indice_glace_sol` remains empty rather than zero. Mountain permafrost in the Andes, New Zealand, or East Africa is therefore missing; a mountain cell whose mean temperature exceeds $+3\ ^\circ\text{C}$ receives 0 even if its peaks host permafrost.
- **Mars ground ice (SWIM).** Consistency ranges from $-1$ (inconsistent with ice) to $+1$; the index retains the highest positive value across the three depth slices, or 0 if none is positive. Depth only considers pixels with consistency $\ge 0.25$ (`SEUIL_SWIM`): a barely positive consistency (e.g., 0.06 at Gale) does not yield an ice depth. With a 0.5 threshold, the 0–1 m slice disappeared almost everywhere (placing Arcadia at 3 m, even though fresh impact craters exposed ice there at depths of a few tens of centimeters, Byrne et al. 2009). SWIM has no values poleward of $\pm 60^\circ$ or above $+1\text{ km}$: left empty, including at high latitudes where ice is certain (Phoenix observed it at ~5 cm depth at 68° N). High consistency does not prove the presence of ice.
- **Moon ground ice (Diviner).** `ice_depth` is the depth at which water ice sublimates at $1\text{ kg/m}^2$ per billion years: 0 = stable at the surface, $-999$ = not stable within 2.87 m. The value $-1$ (undocumented, occurring on triangles with a median maximum temperature of ~77 K, i.e., cold traps) is interpreted as 0. The mesh only exists poleward of 80° (~600 km square around each pole): a cell covered by less than 50% of the mesh remains empty, as does everything closer to the equator.
- **Soil water.** Mars: water-equivalent hydrogen in the top meter measured by neutrons; this also includes water bound in hydrated minerals. Moon: Lunar Prospector hydrogen (a few tens to 200 ppm) multiplied by the $\text{H}_2\text{O}/\text{H}$ mass ratio (8.94); negative values (noise) are clamped to 0. Earth: radiometric soil moisture only senses the top few centimeters: `eau_sol_pct` is a rough **estimate**, and only `eau_sol_rang` is directly comparable across bodies.
- **Permanent shadows.** LOLA maps are in polar stereographic projection; their 240 m pixels are grouped into 4×4 blocks (~1 km) and aggregated into H3 cells. Georeferencing was verified against Shackleton, Faustini, and Haworth (South Pole); total areas (25,564 $\text{km}^2$ in the north, 28,642 $\text{km}^2$ in the south) match the source maps.
- **Open water on Earth.** A JRC pixel is classified as open water if it is inundated at least half the time (occurrence $\ge 50\%$). Ocean pixels are masked out (0.05° land mask; a few coastal pixels may remain). Poleward of 80° N and 60° S, JRC has no tiles: `part_eau_libre` is left empty (northern Greenland, Antarctica).

## Limitations

- Quantities are only comparable across normalized columns: `indice_glace_sol` blends a permafrost fraction (Earth), a data consistency index (Mars), and a stable area fraction (Moon).
- Mars `part_glace_surface` comes from a $3.75^\circ \times 5.6^\circ$ grid: polar caps appear as 220 km blocks.
- Glacier or permafrost fractions averaged over a 250 $\text{km}^2$ cell do not indicate where the ice is located within the cell.
- Moon `part_glace_surface` only exists at the South Pole, and at most on the order of one percent of a cell: M3 only detects isolated pixels inside shadows. Pixel counts for each region are distributed proportionally to area, as their exact coordinates are not published. It is excluded from the Moon's `couverture` metric.
- Source uncertainties are not included in the output tables.