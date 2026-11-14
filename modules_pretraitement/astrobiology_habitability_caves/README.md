# Astrobiology, Habitability, Caves, and Subsurface

Caves, lava tubes, hot springs, mines, karst, volcanoes, and hydrated minerals per H3 cell (resolution 5), for **Earth, Mars, and the Moon**. All three bodies share the exact same columns. An empty column (`NaN`) means "unknown"; it equals 0 when the phenomenon does not exist on that body (no mines on Mars or the Moon, no hot springs on the Moon) or when no object is cataloged in an area where the source actively surveyed.

This module is **independent**: it does not read outputs from any other module. Earth's volcanic context and hydrated minerals are already included in `geology_mineralogy` (columns `litho_basalte`, `litho_volcanique_felsique`, `litho_pyroclastique` and `comp_argile_al`, `comp_argile_fe_mg`, `comp_mica`, `comp_carbonate`, `comp_sulfate`, `comp_silice_hydratee`): downstream comparisons join them on `(body, resolution, h3)` rather than duplicating them here.

This module does not directly measure habitability: it counts **sites of astrobiological interest** (subsurface shelters, hydrothermal water, aqueous alteration, mining activity creating acidic environments) to compare against regions on Mars or the Moon. These inventories represent catalogs of surveyed features rather than exhaustive censuses.

## Files

```
run.sh                        entry point (./pipeline run astrobiology_habitability_caves)
requirements.txt              module dependencies
inputs.txt                    optional input: team's tubes_de_lave.csv
audit.csv                     physical bounds and reference sites (./pipeline audit astrobiology_habitability_caves)
scripts/pretraitement.py      preprocessing script for all three bodies
```

## Sources and Setup

| Body | Source | Used for | How to obtain |
|---|---|---|---|
| Earth | **Maus et al. 2022**, *Global-scale mining polygons v2* (PANGAEA 942325, CC BY-SA 4.0): 44,929 polygons, $101,583\text{ km}^2$ | `part_mine` | automatic (25 MB) |
| Earth | **OpenStreetMap**, `natural=cave_entrance` (73,000 nodes) and `natural=hot_spring` (5,300), via Overpass API (ODbL) | `n_cavites`, `n_tubes_lave`, `n_sources_chaudes` | automatic, two queries cached in `cache/`; takes a few minutes |
| Earth | **Wikidata**, cave (15,000 with coordinates), lava tube (47), and hot spring classes, via SPARQL (CC0) | same, deduplicated against OpenStreetMap | automatic; service rate-limits requests, the module waits automatically |
| Earth | `inputs/astrobiology_habitability_caves/tubes_de_lave.csv` (`nom`, `lat`, `lon`) | `n_tubes_lave` | **optional**, compiled by the team |
| Earth | **WOKAM** (WHYMAP, BGR Berlin, IAH, KIT, UNESCO 2017) via BGR ArcGIS service: 2,805 karstifiable rock polygons and 92 major cave systems | `part_karst`, `n_cavites` | automatic (~1 MB, cached); **mandatory attribution**, see Limitations & Citations |
| Earth | **Smithsonian Global Volcanism Program**, *Volcanoes of the World* (public WFS service): 1,214 Holocene and 1,452 Pleistocene volcanoes | `n_volcans` | automatic (~1 MB); citation required |
| Earth | **Natural Earth** 1:10 m, land areas (public domain) | land cells, karst mask | automatic (3 MB) |
| Mars | **Mars Global Cave Candidate Catalog v1** (Cushing, USGS Astrogeology): 1,062 candidates | `n_cavites`, `n_tubes_lave` | automatic (1.8 MB) |
| Mars | **Hydrated mineral sites** by Carter et al. 2013 (OMEGA and CRISM), ESA archive MEX-M-OMEGA-5-DDR-GLOBAL-MAPS-V1.0: 1,855 sites | `n_sites_aqueux`, `indice_aqueux` | automatic (0.1 MB) |
| Moon | **LROC Lunar Pit Atlas** (Wagner and Robinson 2021): 278 pits | `n_cavites`, `n_tubes_lave` | automatic (0.2 MB, LROC PDS) |
| Moon | **Current Evidence of Lunar Lava Tubes** (Losarcos and Dombard 2026, Zenodo 20516852, CC BY 4.0): 21 radar and geophysical points, 11 gravity anomalies | `n_indices_tubes` | automatic (5 KB) |

Planned sources without open equivalents: **hydrothermal springs** rely solely on OpenStreetMap and Wikidata (no open global terrestrial hot spring database exists); submarine hydrothermal vents (InterRidge) fall outside land cells and are excluded. Terrestrial **lava tubes** are limited to ~100 records (Wikidata and OpenStreetMap names): no open global inventory exists; `tubes_de_lave.csv` is used to supplement them (Hawaii, Iceland, Canary Islands, Lava Beds, Jeju, etc.), while `n_volcans` and `part_karst` provide geological context.

## Running

```bash
./pipeline check astrobiology_habitability_caves
./pipeline run astrobiology_habitability_caves --corps moon          # ~1 min
./pipeline run astrobiology_habitability_caves --corps mars          # ~1 min
./pipeline run astrobiology_habitability_caves --corps earth         # depends on Overpass and Wikidata query times
./pipeline run astrobiology_habitability_caves                       # all three bodies
./pipeline audit astrobiology_habitability_caves
./pipeline publish astrobiology_habitability_caves
```

| Option | Effect |
|---|---|
| `--corps earth mars moon` | bodies to process (default: all three) |
| `--resolution 5` | H3 resolution |
| `--zone W S E N` | restrict computation to a bounding box (testing) |
| `--sans-osm` | Earth: skip OpenStreetMap queries |
| `--sans-wikidata` | Earth: skip Wikidata queries |
| `--tubes-lave /path.csv` | Earth: team's lava tube CSV file (columns `nom,lat,lon`) |

OpenStreetMap and Wikidata responses are cached in `cache/astrobiology_habitability_caves/`: subsequent runs will not re-query the APIs. To refresh them, delete the `osm_*.tsv` and `wikidata_*.csv` files.

Outputs are saved in `pretreatment_data/astrobiology_habitability_caves/`:
`astrobiology_habitability_caves_{earth,mars,moon}_h3_5.parquet` and `{earth,mars,moon}.duckdb`.

## Columns

`body`, `resolution`, `h3`, followed by:

| Column | Earth | Mars | Moon |
|---|---|---|---|
| `n_cavites` [count] | OpenStreetMap cave entrances, plus Wikidata entries and the 92 major WOKAM cave systems with no neighbor within ~1 km; 0 if none cataloged | MGC3 candidates; empty outside the 11 surveyed volcanic provinces | Lunar Pit Atlas pits |
| `n_tubes_lave` [count] | lava tubes (Wikidata, OpenStreetMap entrance names mentioning lava, team CSV file), capped at `n_cavites` | "sky"-type candidates (skylights/openings into a lava tube); empty outside the MGC3 survey | mare pits (possible lava tube skylights) |
| `n_indices_tubes` [count] | empty | empty | indirect lava tube indicators: 21 radar/geophysical points, 11 gravity anomalies (counted at centroid) |
| `n_sources_chaudes` [count] | OpenStreetMap and Wikidata hot springs | empty | 0 |
| `n_volcans` [count] | Holocene and Pleistocene volcanoes (Smithsonian GVP) | empty | empty |
| `part_mine` [0-1] | fraction of the cell covered by mines (Maus et al.) | 0 | 0 |
| `part_karst` [0-1] | fraction of the cell overlying karstifiable rocks (carbonates, evaporites; WOKAM) | empty | 0 |
| `n_sites_aqueux` [count] | empty | hydrated mineral sites from Carter et al. | 0 |
| `indice_aqueux` [0-1] | empty (see `comp_*` in `geology_mineralogy`) | 1 if the cell contains at least one hydrated site, otherwise 0 | 0 |
| `source_inventaire` [text] | `OpenStreetMap + Wikidata` | `MGC3 (USGS)` | `LROC Lunar Pit Atlas` |
| `couverture`, `fiabilite` [0-1] | fraction of available indicators among `n_cavites`, `n_sources_chaudes`, `n_volcans`, `part_mine`, `part_karst`; `fiabilite` = `couverture` (provisional, same rule as other modules) | among `n_cavites`, `indice_aqueux` | among `n_cavites`, `n_indices_tubes` |

## Method

- **Cells.** Mars and Moon: all 2,016,842 cells. Earth: cells containing the center of at least one 0.05° land pixel from Natural Earth.
- **Counts.** Each feature is assigned to the H3 cell containing its point coordinates. A resolution 5 cell covers ~$250\text{ km}^2$ on Earth, ~$72\text{ km}^2$ on Mars, and ~$19\text{ km}^2$ on the Moon.
- **Earth deduplication.** A cave present in both OpenStreetMap and Wikidata is counted only once: any Wikidata record with an OpenStreetMap neighbor within one resolution 8 cell (~1 km) is discarded. OpenStreetMap entrances are not deduplicated against each other: a cave with multiple entrances is counted multiple times.
- **Earth lava tubes.** A lava tube counts as a single entry per resolution 8 cell; `n_tubes_lave` never exceeds `n_cavites`.
- **Mines.** A mine smaller than $1\text{ km}^2$ is assigned to the cell containing its centroid, while larger mines are rasterized via H3 resolution 8 sub-cells; `part_mine` is the mined area divided by the total cell area.
- **Karst.** The 2,805 WOKAM karstifiable rock polygons (simplified to ~2 km) are rasterized at 0.05°; `part_karst` is the fraction of land pixels in the cell whose center falls inside a polygon. WOKAM maps geological potential (soluble rocks), not confirmed cave presence.
- **Volcanoes.** Smithsonian Holocene and Pleistocene volcanoes, deduplicated by volcano number, counted in the cell containing their summit. An edifice straddling two cells is assigned by its summit. 2,292 out of 2,666 volcanoes are counted: the remainder are submarine or on islands too small to generate a land cell.
- **Lunar tube indicators.** Each point counts as 1; each gravity anomaly (multi-kilometer polygon) counts as 1 at its centroid. The 38 sinuous rilles and collapse chains in the same dataset are excluded.
- **Mars MGC3 survey.** The catalog derives from a survey of 11 volcanic provinces (Alba Patera, Tharsis Montes, Elysium Mons, Syrtis Major, etc.). A cell is only populated if it falls within the neighborhood of a resolution 3 (~3°) cell containing a candidate; elsewhere, "no candidates" means "unsurveyed" and is left empty (`NaN`).
- **Mars hydrated sites.** A site corresponds to an OMEGA or CRISM detection point: `indice_aqueux` is 1 if at least one site falls within the cell. The `geology_mineralogy` module has no hydrated minerals for Mars (OMEGA global maps only cover olivine and pyroxene), which is why the Carter et al. catalog is used here. On Earth, hydrated minerals (EMIT) remain in `geology_mineralogy`.
- **MGC3 priorities.** All priority levels (0 to 3) are included: priority 0 indicates that HiRISE has already imaged the candidate, not that it has been ruled out.

## Limitations & Citations

- **Inventory bias.** OpenStreetMap and Wikidata coverage is much denser in Europe and North America than elsewhere: `n_cavites` reflects mapping effort as much as underlying geology. A value of 0 on Earth means "no cataloged caves", not "no caves".
- **Cross-body comparability.** The three bodies are surveyed using fundamentally different methods: cave entrances on Earth, orbital candidates on Mars, and pits $> 6\text{ m}$ across on the Moon. Counts should only be compared via presence/absence or within-body ranks.
- Terrestrial lava tube inventories are highly incomplete (~100 entries).
- Submarine hydrothermal vents are excluded.
- `n_volcans` and `part_karst` only exist for Earth: no equivalent open global catalogs exist for Mars or the Moon (`NaN`); the Moon lacks soluble rocks (0).

### Licenses and Attribution Requirements

- **Maus et al. (2022):** Licensed under CC BY-SA 4.0.
- **Losarcos & Dombard (2026) (Zenodo Lunar Lava Tubes):** Licensed under CC BY 4.0.
- **OpenStreetMap:** Licensed under ODbL, © OpenStreetMap contributors.
- **Wikidata:** Licensed under CC0.
- **Smithsonian Global Volcanism Program (GVP):** Must be cited as *Volcanoes of the World* (Venzke, E., Smithsonian Institution, https://doi.org/10.5479/si.GVP.VOTW5-2025.5.3).
- **WHYMAP WOKAM (BGR):** Does **not** carry a standard Creative Commons license. Per BGR terms of use, you must include the official copyright attribution (*"WHYMAP WOKAM, © BGR Berlin, IAH Reading, KIT Karlsruhe, UNESCO Paris 2017"*), cite the dataset, and fulfill their **reciprocal sharing obligation** by sending a copy or reprint of any resulting publication or final map to `whymap@bgr.de`. Verify both GVP and WOKAM compliance before distributing outputs outside the team.

#### Formal References (APA 7th Edition)

- Chen, Z., Auler, A. S., Bakalowicz, M., Drew, D., Griger, F., Hartmann, J., Jiang, G., Moosdorf, N., Richts, A., Stevanovic, Z., Veni, G., & Goldscheider, N. (2017). *World Karst Aquifer Map (WHYMAP WOKAM)* [Data set]. BGR, IAH, KIT, UNESCO. https://www.whymap.org/whymap/EN/Maps_Data/maps_data_node_en.html *(Attribution: WHYMAP WOKAM, © BGR Berlin, IAH Reading, KIT Karlsruhe, UNESCO Paris 2017; reprint required at whymap@bgr.de)*.
- Global Volcanism Program. (2025). *Volcanoes of the World* (v. 5.3) [Data set]. Distributed by Smithsonian Institution, compiled by Venzke, E. https://doi.org/10.5479/si.GVP.VOTW5-2025.5.3