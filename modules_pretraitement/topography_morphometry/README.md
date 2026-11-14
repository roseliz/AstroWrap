# Topography, Morphometry, and Craters

Terrain morphology of each H3 cell (resolution 5) on **Earth, Mars, and the Moon across all latitudes**: slope distribution, flat terrain fraction, roughness, elevation range, curvature, and crater density.

Slopes depend on pixel size. The pipeline standardizes measurements to a fixed **base resolution**: **500 m** for all three bodies (matching Mars) and **100 m** for Earth and the Moon.

## Files

```text
run.sh                          Pipeline entry point (./pipeline run topography_morphometry)
requirements.txt, inputs.txt    Dependencies; manual drop-in folders for failed downloads
crateres_terre.csv              Confirmed terrestrial impact structures (Earth Impact Database, 189)
scripts/pretraitement.py        Preprocessing script for all three bodies
```

## Sources

All assets download automatically without requiring accounts.

| Body | Source | Purpose | Download & Storage |
| :--- | :--- | :--- | :--- |
| Earth | **Copernicus DEM GLO-90** (ESA), 3″ pixels (~90 m), 1° tiles | Elevation | ~26,000 tiles via AWS Open Data, streamed and deleted (tens of GB transferred, tens of MB local cache) |
| Earth | **Earth Impact Database** (PASSC, University of New Brunswick) | Craters | Bundled in repository (`crateres_terre.csv`) |
| Mars | **MOLA MEGDR** (Mars Global Surveyor), USGS 463 m global mosaic | Elevation | 2 GB, stored in `cache/` |
| Mars | **Robbins & Hynek (2012) Catalog**, ~384,000 craters ($\ge 1\text{ km}$) | Craters | USGS pygeoapi service, stored in `cache/` |
| Moon | **LOLA LDEM** (Lunar Reconnaissance Orbiter), USGS 118 m global mosaic | Elevation | 8 GB, stored in `cache/` |
| Moon | **Robbins (2018) Catalog**, ~1.3 million craters | Craters | USGS Astropedia (~90 MB), stored in `cache/` |

If automatic download fails (firewall, downtime), place the source file manually in the directory specified by `inputs.txt` for priority loading:

* **Mars DEM**: <https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif>
* **Moon DEM**: <https://planetarymaps.usgs.gov/mosaic/Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif>
* **Mars Craters**: [Mars Crater Database (Robbins 2012)](https://astrogeology.usgs.gov/search/map/mars_crater_database_robbins_2012) (place `.tsv` in `inputs/topography_morphometry/crateres_mars/`)
* **Moon Craters**: [Moon Crater Database v1 (Robbins 2018)](https://astrogeology.usgs.gov/search/map/moon_crater_database_v1_robbins) (place `.csv` in `inputs/topography_morphometry/crateres_lune/`)

The script parses latitude, longitude, and diameter columns automatically.

## Execution

```bash
./pipeline check topography_morphometry
./pipeline run topography_morphometry --corps mars       # ~10 min after 2 GB download
./pipeline run topography_morphometry --corps moon       # 30 min to 1 h after 8 GB download
./pipeline run topography_morphometry --corps earth      # Several hours (dominated by downloads)
./pipeline run topography_morphometry                    # Process all three sequentially
```

The three bodies can run concurrently in separate terminals (`--corps earth`, `--corps mars`, `--corps moon`) without write collisions. Requires ~3 GB of RAM per body.

| Option | Effect |
| :--- | :--- |
| `--corps earth mars moon` | Bodies to process (default: all three) |
| `--resolution 5` | H3 resolution |
| `--bases 500 100` | Calculation bases in meters (default: both; Mars supports 500 only) |
| `--crateres-seulement` | Recalculate only `densite_crateres` on existing outputs (seconds) |
| `--zone O S E N` | Earth: restrict download/processing to bounding box degrees (testing) |
| `--telechargements 6` | Earth: parallel tile downloads |
| `--mnt-mars`, `--mnt-lune` | Pre-downloaded DEM file or folder |
| `--crateres-mars`, `--crateres-lune` | Pre-downloaded crater catalogs |
| `--echelle-lune 0.5` | Meters per lunar DEM unit, if undefined in metadata |

Quick test on Earth (Meteor Crater, 4 tiles):
```bash
./pipeline run topography_morphometry --corps earth --zone -112 34 -110 36
```

Outputs are written to `pretreatment_data/topography_morphometry/`: Parquet files (`topography_morphometry_{body}_h3_5_b{500,100}.parquet`) and corresponding tables in `{earth,mars,moon}.duckdb`.

## Output Columns

`body`, `resolution`, `h3`, followed by:

| Column | Definition |
| :--- | :--- |
| `base_m` | Nominal calculation base ($500$ or $100\text{ m}$); compare rows with matching bases only |
| `base_effective_m` | Actual pixel calculation side (Earth $463$ and $93\text{ m}$, Mars $463\text{ m}$, Moon $474$ and $118\text{ m}$) |
| `resolution_source_m` | Original DEM pixel size ($90$, $463$, or $118\text{ m}$) |
| `pente_p10` … `pente_p90` | Slope deciles ($^\circ$) within the cell (for Wasserstein distance) |
| `pente_moy` | Mean slope ($^\circ$) |
| `part_pente_inf_5` | Fraction of pixels with slope $< 5^\circ$ (landing-site suitability) |
| `rugosite_rms` | Root mean square difference between pixel elevation and surrounding $3 \times 3$ window mean ($\text{m}$) |
| `denivele_p5_p95` | Elevation difference between 5th and 95th percentiles ($\text{m}$) |
| `courbure_moy` | Mean curvature ($-\text{elevation Laplacian}$, $\text{km}^{-1}$): $> 0$ convex, $< 0$ concave |
| `courbure_abs_moy` | Mean absolute curvature ($\text{km}^{-1}$): total concavity/convexity intensity |
| `densite_crateres` | Craters of $\ge 1\text{ km}$ diameter per $1,000\text{ km}^2$, counted across the cell and neighbors (see Methodology) |
| `n_pixels` | Calculation pixels used (1 in 9 for Earth at $100\text{ m}$ base) |
| `couverture` | Fraction of cell containing valid DEM elevations (Earth oceans/missing tiles count as empty) |
| `fiabilite` | Equal to `couverture` (provisional placeholder) |

## Methodology

* **Base Resolution**: DEM pixels are block-averaged to reach target bases (Earth $5 \times 5$ pixels of 3″ for $500\text{ m}$, Moon $4 \times 4$ for $500\text{ m}$). Longitudinal convergence near poles is corrected by grouping columns to maintain roughly square pixels up to high latitudes.
* **Slope & Curvature**: Central differences calculated on sphere coordinates; $\text{atan}(|\nabla z|)$. Curvature is the discrete Laplacian; roughness is the $3 \times 3$ mean deviation.
* **Cell Assignment**: Pixels map to H3 cells via center coordinates (computed in $\sim 1/8$ cell sub-blocks). Deciles are exact: DEMs stream North-to-South, computing cells as soon as all constituent pixels pass. Earth at $100\text{ m}$ base uses 1-in-3 subsampling per axis ($\sim 3,000\text{ pixels/cell}$) without affecting deciles.
* **Earth Data**: Elevation $0$ represents sea level (Copernicus outputs $0$ for oceans with missing offshore tiles). Valid cells require at least one terrestrial pixel.
* **Craters**: At resolution 5, individual cells are small (Moon $\sim 19\text{ km}^2$, Mars $\sim 72\text{ km}^2$, Earth $\sim 253\text{ km}^2$) and rarely contain craters. Densities aggregate craters ($\ge 1\text{ km}$) over the target cell plus surrounding annular rings to reach a minimum spatial window of $\sim 1,000\text{ km}^2$ (Earth: 1 ring, $\sim 1,800\text{ km}^2$; Mars: 2 rings, $\sim 1,400\text{ km}^2$; Moon: 4 rings, $\sim 1,100\text{ km}^2$).

## Limitations

* **Gravity Effects**: Equal slopes experience different mechanical stability due to surface gravity variations (Mars $0.38g$, Moon $0.17g$).
* **Elevation Range**: `denivele_p5_p95` varies with H3 cell surface area across latitudes/bodies; compare elevation ranges with caution. Slopes, roughness, and curvature are standardized by base resolution.
* **Terrestrial Craters**: Earth impact structures are heavily eroded ($167$ confirmed $\ge 1\text{ km}$). `densite_crateres` is near zero globally, serving primarily to flag known impact sites (Meteor Crater, Haughton, Ries).
* **Water Bodies**: Flat lake surfaces in Copernicus DEM artifacts artificially inflate `part_pente_inf_5`.
* **Polar Interpolation**: Mars ($> \pm 88^\circ$) and lunar polar DEMs rely on altimeter track interpolations; values are less reliable.
* **High-Resolution Refinement**: Fine local DEMs ($30\text{ m}$, CTX, HiRISE, SLDEM, $5\text{ m}$ polar LOLA) are excluded from this module; targeted high-resolution processing occurs on selected cells post-comparison.