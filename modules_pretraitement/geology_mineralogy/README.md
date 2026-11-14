# Geology, Mineralogy, and Surface Materials

What the surface of each H3 cell (resolution 5 by default) is made of, on **Earth, Mars, and the Moon**: its composition in mineral families and the fraction of each rock class. The two vectors are compared separately.

## Files

```text
requirements.txt            Python dependencies of the module
scripts/pretraitement.py    Preprocessing script for the three bodies (entry point)
scripts/families.py         The 13 mineral families, and the EMIT spectral library mapped onto them
scripts/lithology.py        The 12 rock classes, and the geologic map units assigned to each of them
scripts/emit.py             The Earth zones where EMIT is read, and EMIT granule -> pixel counts per cell
scripts/utils.py            Helpers: free-space check, path display, DuckDB export
```

Paths below are relative to the repository root. The script creates these folders there:

| Folder | Content |
| :--- | :--- |
| `cache/geology_mineralogy/` | Downloaded Mars and Moon data, rasterized GLiM, temporary Earth downloads |
| `inputs/geology_mineralogy/` | Sources to download manually (GLiM, Moon map), or fallback copies |
| `pretreatment_data/geology_mineralogy/` | Outputs (Parquet and DuckDB) |

## Installation

Requires Python 3.10 or later.

```bash
pip install -r modules_pretraitement/geology_mineralogy/requirements.txt
```

The Earth part needs a free [NASA Earthdata](https://urs.earthdata.nasa.gov/) account. `earthaccess` reads the credentials from `~/.netrc`, or from the `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD` environment variables.

## Sources

| Body | Source | Purpose | How to get it |
| :--- | :--- | :--- | :--- |
| Earth | NASA **EMIT L2B MIN** v001 (60 m) | Minerals, over the analogue zones | Automatic, over the zones of `scripts/emit.py` (~90 MB per granule) |
| Earth | NASA **EMIT L3 ASA** v002 (abundances of 10 minerals, 0.5° grid) | Minerals, elsewhere in arid regions (±52°) | Automatic (a single file) |
| Earth | **GLiM** global lithological map (Hartmann and Moosdorf 2012) | Rocks | **Manual**: `LiMW_GIS 2015.gdb` (1.2 GB) in `inputs/geology_mineralogy/glim/` |
| Earth | NASA **MODIS MCD12C1** v061 (0.05°) | Land, vegetation, urban areas | Automatic (1.2 GB, deleted after reading) |
| Mars | **OMEGA** (Mars Express) global maps of olivine, pyroxene and ferric oxides (Ody et al. 2012), 40 pixels per degree | Minerals | Automatic, from the ESA PSA archive (3 × 198 MB) |
| Mars | **USGS SIM 3292 global geologic map** (Tanaka et al. 2014) | Rocks | Automatic (GeoJSON); otherwise the shapefile in `inputs/geology_mineralogy/carte_mars/` |
| Moon | **Olivine, plagioclase and pyroxene abundances** (Lucey et al. 2021, Kaguya MI + Diviner, CC BY 4.0), 32 pixels per degree, ±70° | Minerals | Automatic, from Zenodo (5 × 206 MB) |
| Moon | **Unified Geologic Map of the Moon** (USGS 2020) | Rocks | **Manual**: `GeoUnits.shp` (+ `.dbf`, `.shx`, `.prj`) in `inputs/geology_mineralogy/carte_lune/` |

* **GLiM**: on the [GLiM page](https://www.geo.uni-hamburg.de/geologie/forschung/aquatische-geochemie/glim.html), download the full vector version (`LiMW_GIS 2015.gdb.zip`), unzip it and copy the `LiMW_GIS 2015.gdb` folder as is. The script rasterizes it once at 2 km, which takes a few minutes and several GB of RAM. The result goes to `cache/geology_mineralogy/glim_classes_2km.tif`, and later runs read that file.
* **Moon map**: [Unified Geologic Map of the Moon](https://astrogeology.usgs.gov/search/map/unified_geologic_map_of_the_moon_1_5m_2020), GIS archive. Only `Lunar_GIS/Shapefiles/GeoUnits.*` is used.
* **EMIT L2B** only observes arid regions between ~52° N and ~52° S, in ~75 km scenes, with more than 100,000 granules (~9 TB). The script therefore reads only the analogue zones listed in `EMIT_ZONES` (`scripts/emit.py`, 19 known analogues):
  * at most `--emit-max` granules per zone, least cloudy first. A zone can raise this limit: Rio Tinto, a small and often cloudy target, reads 40;
  * every pixel of each granule;
  * each granule is deleted after reading: ~25 GB transferred in total, a few GB of disk at most.

  To add a zone, add a line to `EMIT_ZONES`.
* **EMIT L3** covers the rest of the arid regions: mean abundances on 0.5° boxes (~55 km), coarser than a cell (~16 km). `source_mineralogie` tells which of the two was used. Outside arid regions (forests, poles, croplands), `comp_*` is empty, but lithology covers all land.

The downloaded Mars and Moon files stay in `cache/geology_mineralogy/`, so later runs do not download them again.

## Running the script

Run these commands from the repository root:

```bash
python modules_pretraitement/geology_mineralogy/scripts/pretraitement.py --bodies moon
```

```bash
python modules_pretraitement/geology_mineralogy/scripts/pretraitement.py --bodies mars
```

```bash
python modules_pretraitement/geology_mineralogy/scripts/pretraitement.py --bodies earth
```

```bash
python modules_pretraitement/geology_mineralogy/scripts/pretraitement.py
```

The first run of the Moon downloads ~1 GB, and the first run of Mars ~800 MB. Earth rasterizes GLiM once, then reads EMIT zone by zone. Without `--bodies`, the last command processes the three bodies.

| Option | Effect |
| :--- | :--- |
| `--bodies earth mars moon` | Bodies to process (default: all three) |
| `--resolution 5` | H3 resolution |
| `--year 2023` | Earth: MCD12C1 year |
| `--glim PATH` | Earth: GLiM folder |
| `--emit-max 12` | Earth: maximum EMIT granules per zone (~90 MB each), least cloudy first |
| `--emit-step 1` | Earth: read one EMIT pixel in N along each direction (2 = 4 times faster, fewer pixels) |
| `--no-emit` | Earth: lithology and masks only |
| `--no-emit-l3` | Earth: no EMIT L3 fill outside the zones |
| `--mars-map PATH`, `--moon-map PATH` | Geologic maps already downloaded |

The script writes to `pretreatment_data/geology_mineralogy/`:

* one Parquet file per body, `geology_mineralogy_{body}_h3_{resolution}.parquet`. Its schema metadata records the families, the visible families, the rock classes and the sources.
* one DuckDB database per body, `{earth,mars,moon}.duckdb`, rebuilt from the Parquet files after each write.

After each body, the script prints a few reference sites (Rio Tinto, Jezero, Apollo 11…) and summary counts as a sanity check, along with the map units it could not classify.

## Output columns

`body`, `resolution`, `h3`, followed by:

| Column | Definition |
| :--- | :--- |
| `comp_<family>` | Composition in 12 mineral families (iron oxides apart). Sums to 1 over the families visible on the body. **NaN** for a family the instrument cannot see, and wherever there is no measurement |
| `part_oxyde_fer` | Fraction of the measured pixels where an iron oxide is detected (Earth EMIT L2B zones, Mars); NaN on the Moon and for EMIT L3 |
| `source_mineralogie` | `EMIT L2B`, `EMIT L3 (0.5 deg)`, `OMEGA`, `Kaguya MI + Diviner`, or empty |
| `litho_<class>` | Fraction of the cell in each rock class; sums to 1 over the mapped part |
| `taux_detection` | Fraction of the measured pixels where at least one mineral is recognized (Moon: 1 when an abundance is measured) |
| `couverture_mineralogie` | Measured area / cell area (0 to 1). In the Earth EMIT L2B zones, it is reduced by the fraction of **dense** vegetation (see below) |
| `couverture_lithologie` | Fraction of the cell covered by a classified map unit |
| `part_vegetation`, `part_artificiel` | Earth: vegetation and urban areas (MCD12C1), to be used as masks; 0 on Mars and the Moon |
| `couverture`, `fiabilite` | Mean of the two coverages; `fiabilite` equals `couverture` for now (same rule as the other modules) |
| `n_mesures`, `n_detecte`, `n_<family>` | Pixel counts (Earth, Mars); Moon: `n_mesures` only |

In the EMIT L2B zones, EMIT cannot see the ground under dense vegetation: forests, closed shrublands, woody savannas, wetlands and croplands. These reduce `couverture_mineralogie`. Open shrublands, savannas and grasslands leave the ground visible and do not.

**Mineral families of the composition** (12, in this order): `pyroxene, olivine, feldspath, mafique_autre, argile_al, argile_fe_mg, mica, carbonate, sulfate, silice_hydratee, sel, autre_mineral`. That is: pyroxene, olivine, feldspar, other mafics, Al clays, Fe/Mg clays, micas, carbonates, sulfates, hydrated silica, salts, other minerals.

**Iron oxides** are kept apart (`part_oxyde_fer`). EMIT gives two minerals per pixel: one near 2.2 µm (group 1: clays, carbonates, sulfates…) and one near 1 µm (group 2), which is almost always an iron oxide. Counted in the composition, iron oxides made up ~50 % everywhere and hid the differences between sites.

| Body | Visible families | How |
| :--- | :--- | :--- |
| Earth | All 12 | EMIT zones: L2B pixels where the family is recognized (group 1 or 2). Elsewhere: EMIT L3 abundances (calcite, dolomite → carbonate; gypsum → sulfate; kaolinite, montmorillonite → argile_al; chlorite, vermiculite → argile_fe_mg; illite + muscovite → mica) |
| Mars | `olivine`, `pyroxene` (and `part_oxyde_fer`) | OMEGA pixels above the Ody et al. (2012) thresholds: olivine OSP1 ≥ 1.04; pyroxene 2 µm band depth ≥ 1 % (the maps only contain these pixels); ferric oxide Fe3+ parameter (0.53 µm band) ≥ 0.20, that is strongly oxidized surfaces. The Fe3+ parameter exists on every observed pixel, so it marks where OMEGA measured |
| Moon | `pyroxene`, `olivine`, `feldspath` | Mean pyroxene, olivine and plagioclase abundances, renormalized |

**Rock classes** (12): `basalte, volcanique_felsique, pyroclastique, plutonique_basique, plutonique_felsique, sedimentaire_clastique, non_consolide, carbonate, evaporite, metamorphique, glace, impact`. That is: basalt, felsic volcanic, pyroclastic, basic plutonic, felsic plutonic, clastic sedimentary, unconsolidated, carbonate, evaporite, metamorphic, ice, impact. The class of each map unit is in `MAP_UNITS` (`scripts/lithology.py`):

* Earth (GLiM first-level class): `vb` → basalte, `py` → pyroclastique, `pb` → plutonique_basique, `ss`/`sm` → sedimentaire_clastique, `su` → non_consolide, `sc` → carbonate, `ev` → evaporite…
* Mars (Tanaka units): volcanic units → basalte; Noachian highlands and the impact unit → impact; basins, transition units, northern plains → sedimentaire_clastique; aprons and polar dunes → non_consolide; polar deposits and cap → glace.
* Moon: maria → basalte; dark mantling deposits → pyroclastique; highlands ("Terra") → plutonique_basique (anorthositic crust); craters, basins, light plains → impact.

The column names and family/class values are the shared output schema and stay as they are.

## Method

* **Cells**: on Earth, the cells containing the center of at least one MCD12C1 land pixel (water < 50 %); on Mars and the Moon, every cell.
* **Lithology**: on Earth, the GLiM class at the center of each 0.05° land pixel of the cell. On Mars and the Moon, the map is rasterized at 0.05° and read at 7 points per cell (center and vertices).
* **Minerals**: counts (Earth, Mars) or abundances (Moon) are summed per cell. The Mars and Moon maps are first grouped into blocks of 4 × 4 pixels. Each cell receives the blocks whose center falls inside it, or, if there are none, the block that contains its center.

## Limitations

* The three instruments do not see the same minerals. Only compare the families visible on both sides (the NaNs make this possible), and never read a NaN as an absence.
* Earth (EMIT L2B) and Mars give **fractions of pixels where a mineral is detected**, while the Moon and EMIT L3 give **abundances**. Compositions compare in shape, not in quantity.
* EMIT L3 only knows 10 minerals (no pyroxene, olivine, feldspar or salt) on ~55 km boxes, so it is coarser than the EMIT L2B zones; filter on `source_mineralogie` if needed.
* EMIT only sees arid regions between ~52° N and ~52° S; OMEGA masks the poles (ice); the lunar abundances stop at ±70°.
* The unit → class assignments are working choices, to be reviewed with the team.
* Martian clays, sulfates and carbonates (CRISM, MOCAAS catalog of Carter et al. 2023) are not used yet: on Mars, `comp_` only covers olivine and pyroxene (plus `part_oxyde_fer`).

## OMEGA data credit

Ody, A., Poulet, F., Langevin, Y., Bibring, J.-P., Bellucci, G., Altieri, F., Gondet, B., Vincendon, M., Carter, J., Manaud, N. (2012): Global maps of anhydrous minerals at the surface of Mars from OMEGA/MEx. *Journal of Geophysical Research: Planets*, 117, E00J14. doi:10.1029/2012JE004117. Data distributed by the ESA Planetary Science Archive. Credit: ESA, J. Carter.
