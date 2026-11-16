# Astrobiology, habitability, caves and subsurface

Caves, lava tubes, hot springs, mines, karst, volcanoes and hydrated minerals for every H3 cell (resolution 5) of the
Earth, Mars and the Moon. In the app it is the **Volcanoes and caves** criterion.

It doesn't measure habitability: it counts **sites of astrobiological interest** (shelters underground, hydrothermal
water, aqueous alteration, acidic mine environments). The inventories are catalogs of surveyed features, not censuses.

| Value | Means |
|---|---|
| `NaN` | Unknown, or not surveyed |
| `0` | None cataloged where the source surveyed, or impossible on that body (no mines on Mars, no hot springs on the Moon) |

The module reads no other module's output. Earth volcanic rocks and hydrated minerals are in
[geology_mineralogy](../geology_mineralogy/README.md) (`litho_*`, `comp_*`): join on `(body, resolution, h3)`.

## Quick start

From the repository root:

```bash
pip install -r modules_pretraitement/astrobiology_habitability_caves/requirements.txt
python modules_pretraitement/astrobiology_habitability_caves/scripts/pretraitement.py --corps moon
```

| Command | Time |
|---|---|
| `--corps moon` | ~1 min |
| `--corps mars` | ~1 min |
| `--corps earth` | a few minutes, depends on Overpass and Wikidata |
| no `--corps` | the three |

OpenStreetMap and Wikidata answers are cached in `cache/astrobiology_habitability_caves/`. To refresh, delete
`osm_*.tsv` and `wikidata_*.csv`. No account needed.

## Columns

Every table starts with `body`, `resolution`, `h3`.

| Column | Earth | Mars | Moon |
|---|---|---|---|
| `n_cavites` | OSM cave entrances + Wikidata + 92 WOKAM major systems with no neighbor within ~1 km | MGC3 candidates; empty outside the 11 surveyed provinces | Lunar Pit Atlas pits |
| `n_tubes_lave` | Lava tubes (Wikidata, OSM names with "lava", team CSV), capped at `n_cavites` | "Sky" candidates (skylights); empty outside MGC3 | Mare pits (possible skylights) |
| `n_indices_tubes` | empty | empty | 21 radar/geophysical points + 11 gravity anomalies |
| `n_sources_chaudes` | OSM and Wikidata hot springs | empty | 0 |
| `n_volcans` | Holocene and Pleistocene volcanoes (GVP) | empty | empty |
| `part_mine` (0–1) | Share of the cell in mines (Maus et al.) | 0 | 0 |
| `part_karst` (0–1) | Share over karstifiable rock (WOKAM) | empty | 0 |
| `n_sites_aqueux` | empty | Hydrated mineral sites (Carter et al.) | 0 |
| `indice_aqueux` (0–1) | empty | 1 if at least one hydrated site | 0 |
| `source_inventaire` | `OpenStreetMap + Wikidata` | `MGC3 (USGS)` | `LROC Lunar Pit Atlas` |
| `couverture`, `fiabilite` | Share available of `n_cavites`, `n_sources_chaudes`, `n_volcans`, `part_mine`, `part_karst` | Of `n_cavites`, `indice_aqueux` | Of `n_cavites`, `n_indices_tubes` |

`fiabilite` = `couverture` for now. Output: `pretreatment_data/astrobiology_habitability_caves/astrobiology_habitability_caves_<body>_h3_5.parquet`, plus `<body>.duckdb`.

## Sources

| Body | Source | For | How |
|---|---|---|---|
| Earth | Maus et al. 2022, Global-scale mining polygons v2 (PANGAEA 942325, CC BY-SA 4.0): 44,929 polygons, 101,583 km² | `part_mine` | Automatic, 25 MB |
| Earth | OpenStreetMap `natural=cave_entrance` (73,000) and `natural=hot_spring` (5,300), Overpass (ODbL) | caves, tubes, hot springs | Automatic, cached |
| Earth | Wikidata caves (15,000), lava tubes (47), hot springs, SPARQL (CC0) | same, deduplicated against OSM | Automatic, waits on rate limits |
| Earth | `inputs/astrobiology_habitability_caves/tubes_de_lave.csv` (`nom`, `lat`, `lon`) | `n_tubes_lave` | **Optional**, compiled by the team |
| Earth | WOKAM (WHYMAP; BGR, IAH, KIT, UNESCO 2017): 2,805 karst polygons, 92 major cave systems | `part_karst`, `n_cavites` | Automatic, ~1 MB; **attribution required** |
| Earth | Smithsonian GVP, Volcanoes of the World: 1,214 Holocene + 1,452 Pleistocene | `n_volcans` | Automatic, ~1 MB; citation required |
| Earth | Natural Earth 1:10 m land | Land cells, karst mask | Automatic, 3 MB |
| Mars | Mars Global Cave Candidate Catalog v1 (Cushing, USGS): 1,062 candidates | `n_cavites`, `n_tubes_lave` | Automatic, 1.8 MB |
| Mars | Hydrated mineral sites, Carter et al. 2013 (OMEGA, CRISM; ESA MEX-M-OMEGA-5-DDR-GLOBAL-MAPS-V1.0): 1,855 sites | `n_sites_aqueux`, `indice_aqueux` | Automatic, 0.1 MB |
| Moon | LROC Lunar Pit Atlas (Wagner and Robinson 2021): 278 pits | `n_cavites`, `n_tubes_lave` | Automatic, 0.2 MB |
| Moon | Current Evidence of Lunar Lava Tubes (Losarcos and Dombard 2026, Zenodo 20516852, CC BY 4.0) | `n_indices_tubes` | Automatic, 5 KB |

| Gap | Why |
|---|---|
| Hot springs | No open global database: OSM and Wikidata only |
| Submarine vents (InterRidge) | Not on land cells |
| Earth lava tubes | ~100 records; the team CSV adds Hawaii, Iceland, Canaries, Lava Beds, Jeju…; `n_volcans` and `part_karst` give context |

## Options

| Option | Effect |
|---|---|
| `--corps earth mars moon` | Bodies (default: all three) |
| `--resolution 5` | H3 resolution |
| `--zone W S E N` | Only this box (tests) |
| `--sans-osm` | Earth: no OpenStreetMap |
| `--sans-wikidata` | Earth: no Wikidata |
| `--tubes-lave /path.csv` | Earth: team lava tube CSV (`nom,lat,lon`) |

## Method

| Topic | Rule |
|---|---|
| Cells | Mars, Moon: all 2,016,842. Earth: cells holding the center of a 0.05° Natural Earth land pixel |
| Counts | Each feature to the cell of its point |
| Earth duplicates | A Wikidata cave with an OSM neighbor within one res-8 cell (~1 km) is dropped. OSM entrances aren't merged: a cave with 3 entrances counts 3 |
| Earth lava tubes | One per res-8 cell; never more than `n_cavites` |
| Mines | < 1 km² to the centroid cell, larger via res-8 sub-cells; mined area / cell area |
| Karst | WOKAM polygons (simplified ~2 km) rasterized at 0.05°: share of land pixels inside. Soluble rock, not confirmed caves |
| Volcanoes | Deduplicated by volcano number, counted at the summit; 2,292 of 2,666 land on a cell (others submarine or tiny islands) |
| Moon tube indicators | Each point = 1; each gravity anomaly = 1 at its centroid; the 38 rilles and collapse chains left out |
| Mars MGC3 | Survey of 11 volcanic provinces (Alba Patera, Tharsis, Elysium, Syrtis…): a cell is filled only near a res-3 cell with a candidate; elsewhere "no candidate" = not surveyed = `NaN`. All priorities 0–3 kept (0 = already imaged by HiRISE) |
| Mars hydrated sites | `indice_aqueux` = 1 if an OMEGA or CRISM detection falls in the cell (geology_mineralogy has only olivine and pyroxene on Mars) |

## Limits

| Limit | Effect |
|---|---|
| Inventory bias | OSM and Wikidata are much denser in Europe and North America: `n_cavites` shows mapping effort as much as geology. Earth 0 = "none cataloged" |
| Different methods | Cave entrances (Earth), orbital candidates (Mars), pits > 6 m (Moon): compare presence or within-body ranks only |
| Earth lava tubes | ~100 entries, very incomplete |
| Earth only | `n_volcans`, `part_karst`: no open global catalog for Mars or the Moon |

## Licenses and attribution

| Source | License, requirement |
|---|---|
| Maus et al. (2022) | CC BY-SA 4.0 |
| Losarcos and Dombard (2026) | CC BY 4.0 |
| OpenStreetMap | ODbL, © OpenStreetMap contributors |
| Wikidata | CC0 |
| Smithsonian GVP | Cite *Volcanoes of the World* (Venzke, E., Smithsonian Institution, https://doi.org/10.5479/si.GVP.VOTW5-2025.5.3) |
| WHYMAP WOKAM (BGR) | **No Creative Commons license.** Show "WHYMAP WOKAM, © BGR Berlin, IAH Reading, KIT Karlsruhe, UNESCO Paris 2017", cite the dataset, and send a copy of any resulting publication or map to `whymap@bgr.de` |

Check GVP and WOKAM terms before sharing outputs outside the team.

**References (APA 7)**

- Chen, Z., Auler, A. S., Bakalowicz, M., Drew, D., Griger, F., Hartmann, J., Jiang, G., Moosdorf, N., Richts, A.,
  Stevanovic, Z., Veni, G., & Goldscheider, N. (2017). *World Karst Aquifer Map (WHYMAP WOKAM)* [Data set]. BGR, IAH,
  KIT, UNESCO. https://www.whymap.org/whymap/EN/Maps_Data/maps_data_node_en.html
- Global Volcanism Program. (2025). *Volcanoes of the World* (v. 5.3) [Data set]. Distributed by Smithsonian
  Institution, compiled by Venzke, E. https://doi.org/10.5479/si.GVP.VOTW5-2025.5.3

## Files

| Path | Content |
|---|---|
| `scripts/pretraitement.py` | Entry point, three bodies |
| `audit.csv` | Physical bounds and reference sites, for `python scripts/audit.py astrobiology_habitability_caves` |
| `requirements.txt` | Dependencies |
