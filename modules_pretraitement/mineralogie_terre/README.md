# Earth Mineralogy (EMIT, 6 Families, Confidence Levels)

For each H3 cell (resolution 5) of the arid regions: the fraction of pixels where each mineral family is detected, at three confidence levels. This module replaces the Earth mineralogy of `geology_mineralogy`.

## Sources and licences

| Data | Purpose | Licence / terms |
| :--- | :--- | :--- |
| NASA EMIT L2B MIN v002, MIN and MINUNCERT files (60 m), [10.5067/EMIT/EMITL2BMIN.002](https://doi.org/10.5067/EMIT/EMITL2BMIN.002) | Identified mineral, band depth, fit score, uncertainty | NASA open data; cite the DOI |
| NASA EMIT L2A MASK v003, [10.5067/EMIT/EMITL2AMASK.003](https://doi.org/10.5067/EMIT/EMITL2AMASK.003) | Clouds (SpecTf), cirrus, water | NASA open data; cite the DOI |
| NASA EMIT L3 ASA v002 (0.5°), [10.5067/EMIT/EMITL3ASA.002](https://doi.org/10.5067/EMIT/EMITL3ASA.002) | Extent of the arid zone, coarse abundances | NASA open data; cite the DOI |
| EMIT mineral grouping matrix (`data/mineral_grouping_matrix_20230503.csv`), repository [emit-sds/emit-sds-l2b](https://github.com/emit-sds/emit-sds-l2b) | Library entry → 10 minerals | Apache 2.0 (`data/LICENSE_emit-sds-l2b.txt`); kept unchanged |
| EMIT L2B v002 library entries 295 to 312 (`mineral_id_matrix_v6.00a6.csv`), missing from the 2023 matrix | Hematite and goethite nano-phases and mixtures | Fractions deduced from the USGS sample names (`V002_ADDITIONS` in `scripts/families.py`) |

Reference sites used to check the thresholds (`scripts/sites.py`, with the source of each one):

* Calibration: White Sands gypsum dunes (NPS; Fryberger 2001), Cuprite (Swayze et al. 2014), Timanfaya lavas (Smithsonian GVP), Rio Tinto (Fernández-Remolar et al. 2005), Western Australian acid lakes (Benison and Bowen 2006), Saharan sand coatings (Caquineau et al. 2002), plus the Pinacate, Pilbara, Simpson Desert and Grand Erg Oriental zones.
* Independent audit (never used for calibration): Meteor Crater (Shoemaker 1963), Wadi Rum, Hoggar (Assekrem).

Access to NASA data needs a free Earthdata account. Set `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD` in the environment, or in a `.env` file at the repository root (never committed).

## Files

```text
requirements.txt              Python dependencies of the module
data/                         Official EMIT grouping matrix and its Apache 2.0 licence (unchanged)
scripts/run.py                Entry point: runs one step (see "Running")
scripts/catalog.py            CMR search of every EMIT L2B granule (metadata only)
scripts/selection.py          Granules -> H3 cells, the K best per cell (arid zone, clouds <= 30 %)
scripts/granule.py            One granule -> counts per H3 cell and per quality class; masks
scripts/batch.py              Loop over a list of granules: download, count, delete; resumable, local or AWS
scripts/calibration_list.py   Granules of the calibration zones
scripts/calibration.py        Threshold evaluation and validation on the reference sites
scripts/merge.py              Per-granule counts -> final table, audit site check
scripts/families.py           The 6 families and their weight per library entry
scripts/thresholds.py         Frozen detection thresholds
scripts/sites.py              Calibration zones, calibration sites and audit sites, with sources
scripts/l3.py                 EMIT L3 reader (GeoTransform grid: the file's lat axis is shifted by 0.5°)
scripts/scale_test.py         Effect of coarser pixels (300 m, 1 km) on the detected fractions
scripts/utils.py              Paths, Earthdata login, DuckDB helpers
```

## Running

Install the dependencies:

```bash
pip install -r modules_pretraitement/mineralogie_terre/requirements.txt
```

Then run these steps in order from the repository root. Each step accepts the options of its script (`--help`).

```bash
python modules_pretraitement/mineralogie_terre/scripts/run.py catalog
```

```bash
python modules_pretraitement/mineralogie_terre/scripts/run.py selection
```

```bash
python modules_pretraitement/mineralogie_terre/scripts/run.py calibration
```

```bash
python modules_pretraitement/mineralogie_terre/scripts/run.py merge
```

1. `catalog`: ~45 min, ~100 MB in `cache/mineralogie_terre/catalogue/`.
2. `selection`: a few minutes; writes the list of granules to process (`selection.parquet`).
3. `calibration` (optional): reports threshold candidates (~45 min, ~31 GB read). The thresholds used stay the ones frozen in `thresholds.py`.
4. **Worldwide processing**: `batch.py --list selection.parquet --source s3 --production`, run on AWS in `us-west-2`: ~38,800 granules, ~5.6 TB read from the NASA buckets, ~1 GB of output. `--source https` does the same from anywhere, at the speed of your connection. Copy the results to `cache/mineralogie_terre/resultats/`.
5. `merge`: builds the final table from those results and checks the audit sites.

## Output

`pretreatment_data/mineralogie_terre/mineralogie_terre_earth_h3_5.parquet` (and `earth.duckdb`), ~213,000 rows, ~26 MB. It holds every cell of the EMIT arid zone (141,442), plus the cells observed outside it by granule edges (~72,000).

| Column | Definition |
| :--- | :--- |
| `det_<family>_faible`, `_moyen`, `_fort` | Fraction of the valid pixels where the family is detected, at the weak, medium or strong level; NaN when no pixel is valid |
| `bd_<family>` | Mean band depth of the pixels detected at the medium level; NaN where the family is not detected |
| `n_valides`, `n_total` | Valid pixels and geolocated pixels, all granules |
| `n_granules` | Granules touching the cell |
| `zone_aride` | Cell of the EMIT arid zone, the only zone where granules were chosen for the cell |
| `couverture` | Fraction of the cell seen in valid pixels by its best granule (0 to 1) |
| `ab_l3_<family>`, `id_case_l3` | EMIT L3 abundance of the 0.5° box containing the cell center (a different quantity from `det_*`), and that box |
| `source`, `resolution_source_m`, `id_case_source` | `L2B` (60 m), `L3` (55 km) or `vide` (no data) |

`det_*` measures the presence and extent of a family, not its content. Under dense vegetation, valid pixels with no detected mineral lower `det_*`.

**Quality filter.** The EMIT arid zone (L3 mask at 0.5°) is not a geological criterion: for example, it leaves out the Hoggar. Outside the zone, the granules were not chosen for the cell (~4.4 per cell instead of ~8.7), so the values are correct but noisier. For comparisons, filter on `couverture >= 0.5` and document the filter. This keeps 96 % of the zone's cells and 75 % of the cells outside. `zone_aride` lets you stay within the original perimeter.

**Scale** (`scale_test.py`, 5 granules). The test uses pixels of 300 m or ~1 km, with linear mixing and the noise of a 60 m pixel (a pessimistic assumption):
* the detected fraction of the 2.2 µm families falls to ~0.7 (300 m) and ~0.6 (1 km) of its 60 m value (median);
* minor phases (< 5 %) almost disappear at 1 km;
* iron oxides do not decrease.

Keep this in mind when comparing with OMEGA (~1 km) or CRISM (18 to 200 m).

## Method

1. **Granules**: v002 only (v001 detects 4 to 25 times more micas, carbonates and clays on the same cells); EMIT arid zone; announced clouds <= 30 %; the 5 best granules per cell.
2. **Minerals**: only the 10 minerals validated by EMIT, in 6 families: `oxyde_fer` (hematite, goethite), `argile_al` (kaolinite, montmorillonite), `argile_fe_mg` (chlorite, vermiculite), `mica` (illite, muscovite), `carbonate` (calcite, dolomite), `sulfate` (gypsum). A library entry counts for a family if it contains at least 10 % of it.
3. **Valid pixels**: geolocated, with no SpecTf-Cloud, cirrus or water flag. The classic cloud flag is not used: it marks very bright surfaces (≈100 % of the White Sands gypsum dunes under a clear sky).
4. **Detection** at three levels: band depth ≥ 2 (`faible`), 3 (`moyen`) or 5 (`fort`) times its uncertainty (`thresholds.py`). The thresholds were fixed in advance, not tuned on the reference sites, and checked on the calibration sites and on the independent audit sites.
5. **Aggregation**: pixel counts per cell (additive), then fractions. No renormalization; NaN = not observed.
