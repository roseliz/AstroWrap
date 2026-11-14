# Wind Dynamics, Erosion, and Atmosphere

Wind capable of mobilizing sand, dunes, bare ground, dust loading, and dust storms, aggregated by **H3 resolution 5 cells**, for **Earth and Mars**. The Moon has no atmosphere, so this module is disabled for the Moon.

Mars' atmosphere is approximately 60 times less dense than Earth's, meaning that raw wind speeds cannot be directly compared.

The feature vector therefore includes **ratios relative to each body's saltation threshold** and **within-body rankings**, calculated using the same definitions for both celestial bodies.

## Files

```text
run.sh                       Entry point (./pipeline run wind_erosion_atmosphere)
requirements.txt             Module dependencies
inputs.txt                   Manual inputs: MCD, MGD3, Earth dunes (optional)
scripts/pretraitement.py     Preprocessing for both celestial bodies
```

## Data Sources and Setup Requirements

| Body | Source | Purpose | How to Obtain |
|---|---|---|---|
| Earth | NASA **MERRA-2 M2TUNXFLX** (`USTAR`, `RHOA`), monthly × hourly averages | Strong winds, air density | Automatic (Earthdata account); 12 × 876 MB |
| Earth | NASA **MERRA-2 M2TMNXAER** (`DUEXTTAU`) | Dust loading | Automatic; 12 × 80 MB |
| Earth | NASA **VIIRS Deep Blue AERDB_D3_VIIRS_SNPP** (daily, 1°) | Dust storms | Automatic; 365 × 3.6 MB |
| Earth | NASA **MODIS MCD12C1** v061 (land cover, 0.05°) | Land areas, bare ground | Automatic; 1 × 1.2 GB |
| Earth | **Global dune map at 0.1° resolution** (Gunn 2026, *Nature Communications*; [dune-world](https://github.com/geomorphlab/dune-world), MIT license) | Dunes | Automatic (26 MB); an alternative map can be placed in `inputs/wind_erosion_atmosphere/dunes_terre/` |
| Mars | **Mars Climate Database v6.2** (LMD), `clim_aveEUV` | Wind, air density, frost, and ice | **Manual setup**, already completed: `inputs/mcd/`. Do not redistribute. |
| Mars | **Montabone Dust Climatology** (Martian Years 24–36) | Dust loading, dust storms | Automatic on first run (CC BY-SA 3.0 license) |
| Mars | **Mars Global Digital Dune Database (MGD3)**, USGS | Dunes | **Manual setup:** On the [65° N – 65° S page](https://pubs.usgs.gov/of/2007/1158/), download the **Shapefiles** folder into `inputs/wind_erosion_atmosphere/mgd3/`. Optional polar datasets: [North](https://pubs.usgs.gov/of/2010/1170), [South](https://pubs.usgs.gov/of/2012/1259). |

Earth datasets are downloaded, read, and deleted sequentially: approximately **14 GB of total data transfers**, but never more than approximately **1.2 GB stored on disk at once**.

A NASA Earthdata account must be configured in `~/.netrc` (handled by `./setup.sh`).

For MERRA-2, authorize the **NASA GESDISC DATA ARCHIVE** application in your Earthdata profile. If another download returns an HTTP 401 or 403 error, similarly authorize the data center application specified in the error message.

### Montabone Dust Climatology

If the automatic Montabone download fails, download `krigedcdod_v2.tar.gz` from the [dust climatology page](https://www-mars.lmd.jussieu.fr/mars/dust_climatology/).

Extract the `dustscenario_MY*.nc` files into:

```text
inputs/wind_erosion_atmosphere/montabone/
```

### Dune Data

Supported vector formats include `.shp`, `.gpkg`, `.geojson`, and `.gml`.

The script:

- Prioritizes files whose names contain `"dune"` (and `"field"`).
- Retains polygon geometries.
- Reprojects geometries to longitude/latitude when necessary.
- Avoids reading the same layer twice when it is provided in two different projections.
- Displays information about the datasets successfully loaded.

Outside the spatial extent of the available files, `part_dunes` is **missing, not zero**.

For Earth, if no file is present in `dunes_terre/`, the script automatically downloads the Gunn (2026) dune map, a binary 0/1 grid indicating dune presence at 0.1° resolution.

Any alternative 0/1 GeoTIFF in geographic longitude/latitude coordinates placed in this directory is also supported.

### Updating Dune Data Without Reprocessing Everything

Use the `--dunes-seulement` option to update dune coverage without rerunning the entire pipeline.

The script reads the existing results, recalculates only `part_dunes` (along with `couverture` and `fiabilite`), and overwrites the corresponding outputs.

No datasets are downloaded again except the dune map.

This operation takes only a few seconds, compared with approximately **35 minutes for a complete Earth processing run**.

## Running the Pipeline

```bash
# Check module requirements
./pipeline check wind_erosion_atmosphere

# Process Mars (~1 minute after Montabone has been downloaded)
./pipeline run wind_erosion_atmosphere --corps mars

# Process Earth (mostly limited by download time)
./pipeline run wind_erosion_atmosphere --corps earth

# Process both celestial bodies
./pipeline run wind_erosion_atmosphere

# Update only dune coverage using existing results
./pipeline run wind_erosion_atmosphere --dunes-seulement

# Publish the results
./pipeline publish wind_erosion_atmosphere
```

### Available Options

| Option | Description |
|---|---|
| `--corps earth mars` | Celestial bodies to process (default: both). |
| `--dunes-seulement` | Recalculate only `part_dunes` in previously generated results. |
| `--resolution 5` | H3 spatial resolution. |
| `--seuil-tempete 1.0` | Visible dust optical depth threshold used to define a storm day. |
| `--annee 2023` | Year of Earth observation data. |
| `--zone W S E N` | Restrict Earth processing to a geographic bounding box (downloads remain global). |
| `--dunes-terre /path` | Earth: directory containing an alternative dune map (vector boundaries or binary 0/1 GeoTIFF). |
| `--mcd /path`, `--mgd3 /path` | Mars: directories containing the MCD and MGD3 datasets. |
| `--annees-mars 30 31 32` | Martian years to use from Montabone (default: 24–36). |

### Output Files

Results are stored in:

```text
pretreatment_data/wind_erosion_atmosphere/
```

Generated files:

```text
wind_erosion_atmosphere_earth_h3_5.parquet
wind_erosion_atmosphere_mars_h3_5.parquet
earth.duckdb
mars.duckdb
```

## Output Columns

Each output table begins with the following identifiers:

`body`, `resolution`, `h3`

| Column | Definition |
|---|---|
| `vent_fort_rel` | `u_etoile_p95 / u_etoile_seuil`: strong wind relative to the body's saltation threshold (1 = sand begins to move). |
| `part_dunes` | Fraction of the H3 cell covered by dune fields (0–1). |
| `part_sol_nu` | Fraction of bare ground (0–1); see Methodology. |
| `poussiere_rang` | Rank of `poussiere_opacite` among cells belonging to the same celestial body: fraction of cells with lower values (0–1; tied values receive the same rank). |
| `tempetes_rang` | Rank of `tempetes_freq`, using the same definition (cells without storms have a value of 0). |
| `u_etoile_p95` | Friction velocity over bare ground, 95th percentile of monthly × hourly averages (m/s). |
| `u_etoile_seuil` | Threshold friction velocity required to initiate saltation (m/s). |
| `densite_air` | Mean annual near-surface air density (kg/m³). |
| `poussiere_opacite` | Earth: dust optical depth at 550 nm. Mars: dust column opacity above the surface (absorption at 9.3 µm). Units differ, so only the rankings are comparable. |
| `tempetes_freq` | Fraction of days (Martian sols for Mars) classified as dust storm days. |
| `couverture`, `fiabilite` | Fraction of the five indicators available; `fiabilite = couverture` (temporary definition, consistent with the thermal module). |

## Methodology (Identical for Both Celestial Bodies)

### 1. Strong Winds

Strong wind conditions are characterized using the **95th percentile of friction velocity (`u*`)**, calculated from monthly × hourly averages over the year:

- **Earth:** 12 × 24 observations from MERRA-2.
- **Mars:** 12 × 12 observations from the MCD.

The same calculation is applied to both celestial bodies, **assuming bare-ground conditions**.

A logarithmic wind profile under neutral atmospheric stability is used:

```text
u* = 0.4 × wind_speed / ln(z / z0)
```

Where:

- `u*`: Friction velocity (m/s).
- `z`: Height of the wind measurement.
- `z0`: Surface roughness length, fixed at 1 cm.

Wind speed is taken from the lowest atmospheric level available in each model:

- **Earth:** `ULML`, `VLML` at height `HLML` (~60 m).
- **Mars:** Approximately 4.5 m above the surface.

The MERRA-2 `USTAR` variable is **not used**, because it incorporates the surface roughness of forests and urban areas.

Using it produced unrealistic results, suggesting that the Amazon rainforest had stronger sand-moving winds than the Bodélé Depression.

### 2. Saltation Threshold

The saltation threshold is calculated using the **Shao and Lu (2000)** formulation:

```text
u*t = √[0.0123 × ((ρ_grain / ρ_air) × g × d
                  + 3 × 10⁻⁴ / (ρ_air × d))]
```

Where:

- `u*t`: Threshold friction velocity (m/s).
- `ρ_grain`: Grain density (kg/m³).
- `ρ_air`: Local air density (kg/m³).
- `g`: Gravitational acceleration (m/s²).
- `d`: Grain diameter, fixed at 100 µm.

**Earth:**

- Grain material: Quartz.
- Grain density: 2650 kg/m³.
- Gravity: 9.81 m/s².
- Approximate threshold: 0.25 m/s.

**Mars:**

- Grain material: Basalt.
- Grain density: 3000 kg/m³.
- Gravity: 3.71 m/s².
- Approximate threshold: 1.3–3.5 m/s, depending on altitude.

### 3. Bare Ground

**Earth:** Bare-ground fraction is calculated from the IGBP `"Barren"` land-cover class in MODIS MCD12C1, relative to the total land area within each cell.

**Mars:** Bare-ground fraction represents the portion of the year during which the surface is free from CO₂ frost and water ice exceeding 1 kg/m².

No vegetation is present on Mars.

### 4. Dust Loading

**Earth:** Annual mean dust optical depth derived from MERRA-2.

**Mars:** Mean total-column dust opacity across the selected Martian years, obtained from the Montabone climatology (`cdodtot`), representing the dust actually present above the surface.

### 5. Dust Storms

A dust storm day is defined as a day when **visible dust optical depth reaches or exceeds 1.0**.

**Earth:**

- Uses VIIRS observations.
- The dominant aerosol type must be classified as `"dust"`.
- Dust optical depth at 550 nm must be ≥ 1.0.
- Only days with valid VIIRS measurements are considered.

**Mars:**

- Uses Montabone dust opacity normalized to 610 Pa (`cdod610`), independent of altitude.
- Converts infrared absorption opacity to visible opacity using a factor of 2.6.
- A storm is detected when:

```text
cdod610 × 2.6 ≥ 1.0
```

### 6. H3 Cell Assignment

**Earth:** Only H3 cells containing the center of at least one MCD12C1 land pixel are retained, with water coverage below 50%.

**Mars:** All H3 cells are included.

Datasets with spatial resolutions coarser than the H3 cells assign the value of the grid point nearest to each cell center, following the same approach as the thermal module.

| Dataset | Spatial Resolution |
|---|---|
| MERRA-2 | 0.5° × 0.625° |
| VIIRS | 1° |
| MCD | 3.75° × 5.625° |
| Montabone | 3° |

### 7. Dune Coverage

`part_dunes` represents the fraction of each H3 cell's surface covered by dune fields.

**Mars — MGD3 Vector Boundaries**

Dune coverage is estimated using H3 subcells at resolution `H3 resolution + 3`.

Each parent cell is subdivided into **343 subcells**, and the proportion of subcell centers falling within dune-field polygons is calculated.

**Earth — Gunn (2026) Raster Map**

Dune coverage is calculated as:

```text
part_dunes = Area of 0.1° dune pixels whose centers
             fall within the H3 cell
             / Total H3 cell area
```

## Limitations

- **Relative comparison only:** Martian climate models have spatial resolutions of several tens of kilometers, limiting the precision of local estimates.

- **Temporal averaging:** Monthly × hourly averages smooth out short-lived wind gusts. Consequently, `vent_fort_rel` represents climatologically strong winds and underestimates peak wind conditions in the same way for both celestial bodies.

- **Earth dust storm detection:** VIIRS observations are limited to clear-sky conditions, and only one year of data is used.

- **Dune dataset resolution:** MGD3 includes dune fields larger than approximately 1 km². The Earth dune map has a spatial resolution of 0.1° (~10 km), corresponding to only 1–3 pixels per H3 cell. As a result, `part_dunes` provides a relatively coarse estimate of dune coverage on Earth.