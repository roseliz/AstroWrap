# Thermal Conditions, Illumination, and Extremes

Surface and air temperatures, radiation, sunlight exposure, and hot/cold extremes, aggregated by **H3 resolution 5 cells** (Earth ~253 km², Mars ~72 km², Moon ~19 km²).

## Files

```text
run.sh                                          Entry point (./pipeline run thermal_light_extrems)
requirements.txt                                Module dependencies
inputs.txt                                      Manual input requirements: MCD for Mars
notebooks/pretraitement_thermique_3_corps.ipynb Complete code for Moon, Earth, and Mars
scripts/lancer_3_corps.py                       Executes the notebook without Jupyter, with configurable options
```

## Data Sources

| | Earth | Moon | Mars |
|---|---|---|---|
| Surface temperature (`lst_*`) | NASA MODIS **MOD11C3** + **MYD11C3** v061 (Terra, Aqua), monthly, 0.05° | NASA LRO **Diviner**, Global Cumulative Product, 0.5° × local time (PDS) | **Mars Climate Database** v6.2 (LMD, CNES, ESA), `tsurf` |
| Air temperature | NASA **MERRA-2** M2SMNXSLV (`T2MMAX`, `T2MMEAN`, `T2MMIN`) | Not available (`NaN`) | MCD, `temp` at the lowest atmospheric level |
| Solar radiation, infrared radiation, clouds | NASA **MERRA-2** M2TMNXRAD (`SWGDN`, `LWGAB`, `CLDTOT`) | Calculated; 0; 0 (no atmosphere) | MCD `fluxsurf_dn_sw`, `fluxsurf_lw`; clouds `NaN` |
| Fraction of time exposed to sunlight | Astronomical calculation | Astronomical calculation; NASA LRO **LOLA** at the poles | Astronomical calculation |

## Prerequisites

`./setup.sh` handles everything except the MCD files. Run `./pipeline check thermal_light_extrems` to identify missing requirements.

| Celestial Body | Requirements |
|---|---|
| Moon | None. PDS files (Diviner, LOLA) are downloaded automatically when the pipeline runs. |
| Earth | A [NASA Earthdata](https://urs.earthdata.nasa.gov) account configured in `~/.netrc`. For MERRA-2, authorize the **NASA GESDISC DATA ARCHIVE** application under Earthdata Profile → Applications → Authorized Apps; otherwise, requests may return HTTP 401 errors. |
| Mars | MCD files must be manually copied into `inputs/mcd/`. |

### Mars Climate Database (MCD)

The **Mars Climate Database** is available free of charge for scientific use upon request from LMD through the [official request form](https://www-mars.lmd.jussieu.fr/MCD_pro/mcd_pro.html).

By requesting access, users agree **not to redistribute the database to third parties, even partially**. Therefore, MCD files must not be committed to Git or included in any release.

The pipeline requires the 12 files named `clim_01_me.nc` through `clim_12_me.nc`, located in the `data/clim_aveEUV` directory.

```bash
mkdir -p inputs/mcd
tar -xzf MCD_6.2.tar.gz -C inputs/mcd --wildcards '*clim_aveEUV/clim_??_me.nc'
```

If these files are unavailable, the module processes Earth and the Moon while skipping Mars and displaying an informational message.

### Hardware Requirements

- **Temporary storage:** 3–4 GB for downloads in `cache/thermal_light_extrems/`, with files progressively deleted.
- **Memory:** At least 8 GB of RAM for Earth processing.
- **Lower-resource systems:** Process one celestial body at a time.

## Running the Pipeline

```bash
# First test: Mars (~1 minute, local files)
./pipeline run thermal_light_extrems --corps mars

# Moon (~2.8 GB of Diviner data to download)
./pipeline run thermal_light_extrems --corps moon

# Earth: limited geographic region
./pipeline run thermal_light_extrems --corps earth --zone -115 31 -109 37

# Process all three celestial bodies
./pipeline run thermal_light_extrems

# Publish the results
./pipeline publish thermal_light_extrems --note "Earth 2023, Moon, Mars"
```

### Available Options

| Option | Description |
|---|---|
| `--corps moon earth mars` | Celestial bodies to process (default: all three). |
| `--annee 2023` | Year of Earth observation data. |
| `--zone W S E N` | Restricts Earth processing to a bounding box defined by west, south, east, and north coordinates. This reduces computation time, but MODIS and MERRA-2 files are global, so download sizes remain unchanged. |
| `--mcd /path` | Custom MCD directory instead of `inputs/mcd/`. |
| `--resolution 5` | H3 spatial resolution. |

The source code is maintained in the notebook. The `scripts/lancer_3_corps.py` script executes notebook cells sequentially and overrides parameters using command-line options.

**Modifying the notebook is sufficient to update the processing logic.**

The notebook can also be opened directly in VS Code using the `analogues-pipeline (.venv)` kernel.

### Output Directory

Generated datasets are stored at the repository root:

```text
pretreatment_data/thermal_light_extrems/
```

## Output Columns

Each output table begins with three common identifiers:

- `body`
- `resolution`
- `h3`

| Table | Columns |
|---|---|
| `thermal` | `lst_day_mean/min/max`, `lst_night_mean/min/max`, `air_temperature_mean/min/max` |
| `illumination` | `shortwave_radiation_mean`, `longwave_radiation_mean`, `sunshine_duration_mean`, `daylight_duration_mean`, `cloud_fraction_mean`, `daylight_fraction`, `daylight_fraction_min`, `daylight_fraction_max` |
| `extremes` | `lst_day_p05/p95`, `lst_night_p05/p95`, `air_temperature_p05/p95`, `hot_pixel_count`, `cold_pixel_count`, `hot_fraction`, `cold_fraction` |
| All three tables | `pixel_count`, `valid_pixel_count`, `masked_pixel_count`, `coverage`, `source_resolution_km`, `reliability` |

### Units

- **Temperature:** Kelvin (K)
- **Radiation:** W/m²
- **Duration:** Hours per celestial-body cycle:
  - Earth: 24 hours
  - Mars: 24.66 hours
  - Moon: 708.7 hours
- **Normalized values:** `daylight_fraction*`, `coverage`, `reliability`, `hot_fraction`, and `cold_fraction` range from 0 to 1.

## Data Processing Conventions

### 1. Daytime and Nighttime Observations

Daytime and nighttime periods are defined using MODIS satellite overpass times in local solar time:

- **Daytime:** 10:30 AM and 1:30 PM
- **Nighttime:** 10:30 PM and 1:30 AM

For Mars, MCD data is interpolated to these exact observation times.

For the Moon, Diviner measurements are collected at 15-minute intervals between 10:30 AM and 1:30 PM for daytime observations, and between 10:30 PM and 1:30 AM for nighttime observations.

### 2. Temperature Extremes

Temperature extremes are defined **relative to each celestial body**, rather than using universal temperature thresholds.

An observation is classified as:

- **Hot:** Above the 90th percentile of daytime temperatures for that celestial body.
- **Cold:** Below the 10th percentile of daytime temperatures for that celestial body.

Percentiles are calculated using surface-area-weighted observations.

Fixed thresholds such as 313 K and 253 K were not suitable for cross-planetary comparisons:

- Mars never reaches 313 K in the dataset.
- The Moon frequently exceeds 313 K during daytime.

Body-specific thresholds are saved in:

```text
seuils_extremes_<body>.json
```

This approach enables meaningful comparisons of relative thermal extremes across Earth, the Moon, and Mars.

### 3. Daylight Duration

`daylight_fraction` represents the average fraction of time a location receives sunlight over one year.

Its value is approximately **0.5 across most locations**, except at the lunar poles, where local terrain affects illumination and LOLA data is used.

Latitude-dependent variations are primarily captured through:

- `daylight_fraction_min`: Fraction of daylight during the shortest day of the year.
- `daylight_fraction_max`: Fraction of daylight during the longest day of the year.

Interpretation:

- **0:** Continuous darkness (polar night).
- **1:** Continuous sunlight (midnight sun).

At the lunar poles, these values are scaled using the average illumination derived from LOLA.

This is an approximation because the LOLA data used provides only average illumination.

### 4. Data Reliability

The `reliability` metric evaluates the quality of spatial representation based on data coverage and the relationship between source pixel size and H3 cell size.

The reliability formula is:

```text
reliability = coverage / (1 + log2(source_pixel_size / cell_size))
```

Reliability is set to **1 when the source resolution is at least as fine as the H3 cell resolution**, assuming full coverage.

#### Source Spatial Resolutions

| Celestial Body | Dataset | Approximate Resolution |
|---|---|---|
| Earth | MODIS | 5.6 km |
| Earth | MERRA-2 (illumination) | 62 km |
| Moon | Diviner | 15.2 km |
| Mars | MCD | 272 km |

For example, the reliability score for Mars is approximately **0.17**, because a single MCD source pixel represents roughly 700 H3 cells.

This metric helps identify areas where the spatial resolution of the original dataset limits the precision of the resulting analysis.

### 5. Observation Counts and Masking

An observation corresponds to:

**One source pixel × one observation date**

Currently:

```text
masked_pixel_count = 0
```

No land-cover mask has been applied.

### 6. Earth-Specific Considerations

For Earth:

- MODIS surface temperatures are extracted only over land.
- Cloud-covered observations are excluded by MODIS itself.
- Surface temperature measurements therefore represent **clear-sky conditions only**.

This limitation should be considered when comparing Earth's surface temperatures with lunar and Martian datasets.