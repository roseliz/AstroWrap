# Geology, mineralogy and surface materials

What the surface of every H3 cell (resolution 5) is made of, on the Earth, Mars and the Moon: a **composition in
mineral families** and a **share of each rock class**. In the app it is the **Rocks** criterion, which compares the
rock classes only: the mineral columns stay in the output but are not compared (see the
[modules README](../README.md#modules)).

## Quick start

From the repository root (Python 3.10+):

```bash
pip install -r modules_pretraitement/geology_mineralogy/requirements.txt
python modules_pretraitement/geology_mineralogy/scripts/pretraitement.py --bodies moon
```

| Command | First run |
|---|---|
| `--bodies moon` | downloads ~1 GB (needs the Moon map, manual) |
| `--bodies mars` | downloads ~800 MB |
| `--bodies earth` | rasterizes GLiM once, then reads EMIT zone by zone (~25 GB transferred, deleted as it goes) |
| no `--bodies` | the three |

Earth needs a free [NASA Earthdata](https://urs.earthdata.nasa.gov/) account (`~/.netrc`, or
`EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD`). Mars and Moon downloads stay in `cache/geology_mineralogy/`.

## Example: what a cell looks like

| Body | Minerals seen | Rocks from |
|---|---|---|
| Earth | all 12 families | GLiM map |
| Mars | olivine, pyroxene (+ iron oxides) | USGS global map (Tanaka 2014) |
| Moon | pyroxene, olivine, feldspar | Unified Geologic Map |

So a Jezero cell can only be compared with an Earth cell on olivine and pyroxene: the other families are `NaN` on
Mars, **unknown, not absent**.

## Sources

| Body | Source | For | How |
|---|---|---|---|
| Earth | EMIT L2B MIN v001, 60 m | Minerals, in 19 analog zones | Automatic, ~90 MB per granule |
| Earth | EMIT L3 ASA v002, 10 minerals, 0.5° | Minerals, other arid regions (±52°) | Automatic, one file |
| Earth | GLiM (Hartmann and Moosdorf 2012) | Rocks | **Manual**, 1.2 GB |
| Earth | MODIS MCD12C1 v061, 0.05° | Land, vegetation, urban | Automatic, 1.2 GB, deleted after reading |
| Mars | OMEGA olivine, pyroxene, ferric oxides (Ody et al. 2012), 40 px/° | Minerals | Automatic, ESA PSA, 3 × 198 MB |
| Mars | USGS SIM 3292 geologic map (Tanaka et al. 2014) | Rocks | Automatic (GeoJSON), or shapefile in `carte_mars/` |
| Moon | Olivine, plagioclase, pyroxene (Lucey et al. 2021, Kaguya MI + Diviner, CC BY 4.0), 32 px/°, ±70° | Minerals | Automatic, Zenodo, 5 × 206 MB |
| Moon | Unified Geologic Map of the Moon (USGS 2020) | Rocks | **Manual** |

### Manual files

Into `inputs/geology_mineralogy/` (repository root):

| File | Where to get it | Put it in |
|---|---|---|
| `LiMW_GIS 2015.gdb` (folder) | [GLiM page](https://www.geo.uni-hamburg.de/geologie/forschung/aquatische-geochemie/glim.html), full vector version, unzipped | `glim/` |
| `GeoUnits.shp` + `.dbf`, `.shx`, `.prj` | [Unified Geologic Map](https://astrogeology.usgs.gov/search/map/unified_geologic_map_of_the_moon_1_5m_2020), GIS archive, `Lunar_GIS/Shapefiles/` | `carte_lune/` |

GLiM is rasterized once at 2 km (a few minutes, several GB of RAM) into `cache/geology_mineralogy/glim_classes_2km.tif`.

### EMIT on Earth

| | EMIT L2B | EMIT L3 |
|---|---|---|
| Where | 19 analog zones (`EMIT_ZONES` in `scripts/emit.py`) | the rest of arid land, ±52° |
| Detail | every 60 m pixel | 0.5° boxes (~55 km), coarser than a cell |
| How much | `--emit-max` granules per zone, least cloudy first (Rio Tinto: 40) | one file |
| Minerals | 12 families | 10 minerals |

EMIT L2B has over 100,000 granules (~9 TB), hence the zones. To add one, add a line to `EMIT_ZONES`.
Outside arid land (forests, poles, crops) `comp_*` is empty, but rocks cover all land.

## Options

| Option | Effect |
|---|---|
| `--bodies earth mars moon` | Bodies (default: all three) |
| `--resolution 5` | H3 resolution |
| `--year 2023` | Earth: MCD12C1 year |
| `--glim PATH` | Earth: GLiM folder |
| `--emit-max 12` | Earth: EMIT granules per zone |
| `--emit-step 1` | Earth: one EMIT pixel in N per axis (2 = 4× faster) |
| `--no-emit` | Earth: rocks and masks only |
| `--no-emit-l3` | Earth: no EMIT L3 outside the zones |
| `--mars-map PATH`, `--moon-map PATH` | Geologic maps already downloaded |

## Output

`pretreatment_data/geology_mineralogy/geology_mineralogy_<body>_h3_5.parquet`, plus `<body>.duckdb`.
After each body, the script prints reference sites (Rio Tinto, Jezero, Apollo 11…) and the map units it could not classify.

| Column | Meaning |
|---|---|
| `body`, `resolution`, `h3` | Cell |
| `comp_<family>` | Composition in 12 families; sums to 1 over the families visible on the body; `NaN` if not visible or not measured |
| `part_oxyde_fer` | Share of measured pixels with an iron oxide (Earth L2B, Mars); `NaN` on the Moon and for L3 |
| `source_mineralogie` | `EMIT L2B`, `EMIT L3 (0.5 deg)`, `OMEGA`, `Kaguya MI + Diviner`, or empty |
| `litho_<class>` | Share of the cell in each rock class; sums to 1 over the mapped part |
| `taux_detection` | Share of measured pixels with at least one mineral (Moon: 1 when measured) |
| `couverture_mineralogie` | Measured area / cell area; in L2B zones, minus **dense** vegetation |
| `couverture_lithologie` | Share of the cell with a classified map unit |
| `part_vegetation`, `part_artificiel` | Earth vegetation and urban (MCD12C1), for masks; 0 on Mars and the Moon |
| `couverture`, `fiabilite` | Mean of the two coverages; `fiabilite` = `couverture` for now |
| `n_mesures`, `n_detecte`, `n_<family>` | Pixel counts (Earth, Mars); Moon: `n_mesures` only |

Dense vegetation (forests, closed shrublands, woody savannas, wetlands, crops) hides the ground from EMIT.
Open shrublands, savannas and grasslands don't.

### Mineral families (12)

| Value | Family | Value | Family |
|---|---|---|---|
| `pyroxene` | pyroxene | `carbonate` | carbonates |
| `olivine` | olivine | `sulfate` | sulfates |
| `feldspath` | feldspar | `silice_hydratee` | hydrated silica |
| `mafique_autre` | other mafics | `sel` | salts |
| `argile_al` | Al clays | `mica` | micas |
| `argile_fe_mg` | Fe/Mg clays | `autre_mineral` | other minerals |

Iron oxides are kept apart (`part_oxyde_fer`): EMIT gives one mineral near 2.2 µm and one near 1 µm, almost always
an iron oxide. Counted in, they made up ~50% everywhere and hid the differences.

| Body | Visible | How |
|---|---|---|
| Earth | all 12 | L2B pixels where the family is recognized; elsewhere L3 (calcite, dolomite → carbonate; gypsum → sulfate; kaolinite, montmorillonite → argile_al; chlorite, vermiculite → argile_fe_mg; illite + muscovite → mica) |
| Mars | olivine, pyroxene (+ `part_oxyde_fer`) | OMEGA above Ody et al. thresholds: olivine OSP1 ≥ 1.04; pyroxene 2 µm band ≥ 1%; Fe3+ (0.53 µm) ≥ 0.20, which also marks where OMEGA measured |
| Moon | pyroxene, olivine, feldspar | Mean abundances, renormalized |

### Rock classes (12)

`basalte` basalt, `volcanique_felsique` felsic volcanic, `pyroclastique` pyroclastic, `plutonique_basique` basic
plutonic, `plutonique_felsique` felsic plutonic, `sedimentaire_clastique` clastic sedimentary, `non_consolide`
unconsolidated, `carbonate`, `evaporite`, `metamorphique` metamorphic, `glace` ice, `impact`.

| Body | Map units → class (full list: `MAP_UNITS` in `scripts/lithology.py`) |
|---|---|
| Earth (GLiM) | `vb` → basalte, `py` → pyroclastique, `pb` → plutonique_basique, `ss`/`sm` → sedimentaire_clastique, `su` → non_consolide, `sc` → carbonate, `ev` → evaporite… |
| Mars (Tanaka) | volcanic → basalte; Noachian highlands, impact unit → impact; basins, transition, northern plains → sedimentaire_clastique; aprons, polar dunes → non_consolide; polar deposits and cap → glace |
| Moon | maria → basalte; dark mantling deposits → pyroclastique; highlands → plutonique_basique; craters, basins, light plains → impact |

Column names and values are the shared schema: they stay in French.

## Method

| Step | Earth | Mars, Moon |
|---|---|---|
| Cells | Cells holding the center of a MCD12C1 land pixel (water < 50%) | All cells |
| Rocks | GLiM class at the center of each 0.05° land pixel | Map rasterized at 0.05°, read at 7 points per cell (center + vertices) |
| Minerals | Counts summed per cell | Maps grouped in 4 × 4 blocks; each cell gets the blocks centered inside it, or the block holding its center |

## Limits

| Limit | Effect |
|---|---|
| Different instruments | Compare only families visible on both sides; never read `NaN` as absent |
| Detections vs abundances | Earth L2B and Mars give shares of pixels with a detection; Moon and L3 give abundances: compare the shape, not the quantity |
| EMIT L3 | 10 minerals (no pyroxene, olivine, feldspar, salt) on ~55 km boxes; filter on `source_mineralogie` if needed |
| Coverage | EMIT ±52° arid only; OMEGA masks the poles; Moon abundances stop at ±70° |
| Unit → class | Working choices, to review with the team |
| Martian clays, sulfates, carbonates | CRISM / MOCAAS (Carter et al. 2023) not used yet |

## Files

| Path | Content |
|---|---|
| `scripts/pretraitement.py` | Entry point, three bodies |
| `scripts/families.py` | 13 mineral families (12 + iron oxides), EMIT library mapped onto them |
| `scripts/lithology.py` | 12 rock classes and the map units of each |
| `scripts/emit.py` | EMIT zones, granule → pixel counts per cell |
| `scripts/utils.py` | Free space, paths, DuckDB export |
| `cache/geology_mineralogy/` | Mars and Moon downloads, rasterized GLiM |
| `inputs/geology_mineralogy/` | Manual files |

## OMEGA data credit

Ody, A., Poulet, F., Langevin, Y., Bibring, J.-P., Bellucci, G., Altieri, F., Gondet, B., Vincendon, M., Carter, J.,
Manaud, N. (2012): Global maps of anhydrous minerals at the surface of Mars from OMEGA/MEx. *Journal of Geophysical
Research: Planets*, 117, E00J14. doi:10.1029/2012JE004117. Data distributed by the ESA Planetary Science Archive.
Credit: ESA, J. Carter.
