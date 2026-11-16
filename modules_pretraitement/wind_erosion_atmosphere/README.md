# Wind, erosion and atmosphere

Wind able to move sand, dunes, bare ground, dust and dust storms for every H3 cell (resolution 5) of the Earth and
Mars. The Moon has no atmosphere, so it is left out. In the app it is the **Wind and dust** criterion.

The Martian air is ~60 times thinner, so raw wind speeds can't be compared. The module compares **ratios to each
body's sand-moving threshold** and **ranks within each body**, computed the same way on both.

| Comparable | Not comparable |
|---|---|
| `vent_fort_rel` (1 = sand starts moving, on either body) | raw `u_etoile_p95` |
| `poussiere_rang`, `tempetes_rang` (0 to 1, within the body) | raw `poussiere_opacite` (different wavelengths) |
| `part_dunes`, `part_sol_nu` (shares of the cell) | |

## Quick start

From the repository root:

```bash
pip install -r modules_pretraitement/wind_erosion_atmosphere/requirements.txt
python modules_pretraitement/wind_erosion_atmosphere/scripts/pretraitement.py --corps mars
```

| Command | Time |
|---|---|
| `--corps mars` | ~1 min, once Montabone is downloaded |
| `--corps earth` | ~35 min, mostly downloads (~14 GB transferred, never more than ~1.2 GB on disk) |
| no `--corps` | both |
| `--dunes-seulement` | seconds: recomputes `part_dunes`, `couverture`, `fiabilite` in the existing outputs |

Earth needs a [NASA Earthdata](https://urs.earthdata.nasa.gov) account in `~/.netrc`, with the **NASA GESDISC DATA
ARCHIVE** application authorized in the profile. On another HTTP 401 or 403, authorize the data center the error names.

## Sources

| Body | Source | For | How |
|---|---|---|---|
| Earth | MERRA-2 M2TUNXFLX (`USTAR`, `RHOA`), monthly × hourly | Strong winds, air density | Automatic, 12 × 876 MB |
| Earth | MERRA-2 M2TMNXAER (`DUEXTTAU`) | Dust | Automatic, 12 × 80 MB |
| Earth | VIIRS Deep Blue AERDB_D3_VIIRS_SNPP, daily, 1° | Dust storms | Automatic, 365 × 3.6 MB |
| Earth | MODIS MCD12C1 v061, 0.05° | Land, bare ground | Automatic, 1.2 GB |
| Earth | Global dune map 0.1° (Gunn 2026, *Nature Communications*, [dune-world](https://github.com/geomorphlab/dune-world), MIT) | Dunes | Automatic, 26 MB |
| Mars | Mars Climate Database v6.2 (LMD), `clim_aveEUV` | Wind, air density, frost, ice | **Manual**, `inputs/mcd/`; never redistribute |
| Mars | Montabone dust climatology, Martian years 24–36 (CC BY-SA 3.0) | Dust, storms | Automatic on first run |
| Mars | Mars Global Digital Dune Database (MGD3), USGS | Dunes | **Manual** |

### Manual files

Into `inputs/wind_erosion_atmosphere/` (repository root):

| Data | Where to get it | Put it in |
|---|---|---|
| MGD3 | [65° N – 65° S page](https://pubs.usgs.gov/of/2007/1158/), the **Shapefiles** folder; optional poles: [North](https://pubs.usgs.gov/of/2010/1170), [South](https://pubs.usgs.gov/of/2012/1259) | `mgd3/` |
| Montabone, if the download fails | `krigedcdod_v2.tar.gz` from the [dust climatology page](https://www-mars.lmd.jussieu.fr/mars/dust_climatology/), the `dustscenario_MY*.nc` files | `montabone/` |
| Another Earth dune map (optional) | Vector boundaries, or a 0/1 GeoTIFF in lon/lat | `dunes_terre/` |
| MCD | See [thermal_light_extrems](../thermal_light_extrems/README.md#mars-climate-database) | `inputs/mcd/` |

Dune files: `.shp`, `.gpkg`, `.geojson`, `.gml`. Files named `dune` (and `field`) first, polygons only, reprojected
to lon/lat, the same layer never read twice. Outside the files' extent, `part_dunes` is **missing, not 0**.

## Options

| Option | Effect |
|---|---|
| `--corps earth mars` | Bodies (default: both) |
| `--dunes-seulement` | Only recompute `part_dunes` |
| `--resolution 5` | H3 resolution |
| `--seuil-tempete 1.0` | Visible dust optical depth of a storm day |
| `--annee 2023` | Year of the Earth data |
| `--zone W S E N` | Earth: only this box (downloads stay global) |
| `--dunes-terre /path` | Earth: other dune map |
| `--mcd /path`, `--mgd3 /path` | Mars: MCD and MGD3 folders |
| `--annees-mars 30 31 32` | Martian years from Montabone (default: 24–36) |

## Output

`pretreatment_data/wind_erosion_atmosphere/wind_erosion_atmosphere_<earth|mars>_h3_5.parquet`, plus `<body>.duckdb`.

| Column | Meaning | Unit |
|---|---|---|
| `body`, `resolution`, `h3` | Cell | |
| `vent_fort_rel` | `u_etoile_p95 / u_etoile_seuil`: 1 = sand starts moving | |
| `part_dunes` | Share of the cell in dune fields | 0–1 |
| `part_sol_nu` | Share of bare ground | 0–1 |
| `poussiere_rang` | Share of the body's cells with less dust (ties: same rank) | 0–1 |
| `tempetes_rang` | Same, for `tempetes_freq` (no storm: 0) | 0–1 |
| `u_etoile_p95` | Friction velocity over bare ground, 95th percentile | m/s |
| `u_etoile_seuil` | Friction velocity that starts saltation | m/s |
| `densite_air` | Mean near-surface air density | kg/m³ |
| `poussiere_opacite` | Earth: dust optical depth at 550 nm. Mars: column dust opacity at 9.3 µm | |
| `tempetes_freq` | Share of days (sols) with a dust storm | 0–1 |
| `couverture`, `fiabilite` | Share of the 5 indicators available; `fiabilite` = `couverture` for now | 0–1 |

## Method (same on both bodies)

| Indicator | Earth | Mars |
|---|---|---|
| Strong wind | 95th percentile of `u*` over 12 months × 24 h (MERRA-2) | 12 months × 12 times (MCD) |
| Wind level | `ULML`, `VLML` at `HLML` (~60 m) | ~4.5 m |
| Sand grains | quartz, 2,650 kg/m³, g = 9.81 | basalt, 3,000 kg/m³, g = 3.71 |
| Threshold `u*t` | ~0.25 m/s | ~1.3 to 3.5 m/s, with altitude |
| Bare ground | IGBP "Barren" share of land (MCD12C1) | Share of the year free of CO₂ frost and of water ice > 1 kg/m² |
| Dust | Annual mean dust optical depth (MERRA-2) | Mean column opacity `cdodtot` (Montabone) |
| Storm day | VIIRS, aerosol type "dust" and 550 nm depth ≥ 1.0, valid days only | `cdod610 × 2.6 ≥ 1.0` (infrared to visible) |
| Dunes | Area of 0.1° dune pixels centered in the cell / cell area | Share of the 343 sub-cells (res + 3) centered in a dune polygon |
| Cells | Cells holding the center of an MCD12C1 land pixel (water < 50%) | All cells |

Formulas, with grains of `d` = 100 µm and `z0` = 1 cm:

```text
u*  = 0.4 × wind_speed / ln(z / z0)                                   neutral log profile, bare ground
u*t = √[0.0123 × ((ρ_grain / ρ_air) × g × d + 3×10⁻⁴ / (ρ_air × d))]   Shao and Lu (2000)
```

MERRA-2 `USTAR` is **not** used: it includes the roughness of forests and cities, and made the Amazon windier for
sand than the Bodélé Depression.

Coarse sources take the grid point nearest to the cell center (as in the thermal module):

| Source | Grid |
|---|---|
| MERRA-2 | 0.5° × 0.625° |
| VIIRS | 1° |
| MCD | 3.75° × 5.625° |
| Montabone | 3° |

## Limits

| Limit | Effect |
|---|---|
| Martian models | Tens of km per pixel: relative comparison only |
| Monthly × hourly means | Gusts are smoothed: `vent_fort_rel` underestimates peaks, the same way on both bodies |
| Earth storms | VIIRS sees clear skies only, one year of data |
| Dunes | MGD3 keeps fields > ~1 km²; the Earth map is 0.1° (~10 km), 1 to 3 pixels per cell |

## Files

| Path | Content |
|---|---|
| `scripts/pretraitement.py` | Entry point, both bodies |
| `requirements.txt` | Dependencies |
| `inputs/wind_erosion_atmosphere/` | Manual files: MGD3, Montabone, Earth dunes |
