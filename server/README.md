# AstroWrap server: data sources

| Source | Used for | Provider | Terms |
|---|---|---|---|
| Preprocessing module results (`pretreatment_data/`) | Every similarity score, site card values | This project (`modules_pretraitement/`) | See each module's README |
| [WDPA](https://www.protectedplanet.net) (World Database on Protected Areas) | Protected and strictly protected share of each site | UNEP-WCMC and IUCN | Non-commercial use; derived values only, with the citation and version |
| [OurAirports](https://ourairports.com/data/) | Nearest airport with scheduled flights | OurAirports | Public domain |
| [Global-scale mining polygons](https://doi.org/10.1594/PANGAEA.942325) (Maus et al. 2022) | Mine share of each site | Maus et al., PANGAEA | CC BY-SA 4.0 |
| [Natural Earth](https://www.naturalearthdata.com) (geography regions, countries) | Place names (deserts, mountain ranges, countries) | Natural Earth | Public domain |
| [OpenStreetMap Nominatim](https://nominatim.openstreetmap.org) | Locality, region and country of a site | OpenStreetMap contributors | ODbL; at most 1 request per second, results cached |
| [MOLA](https://astrogeology.usgs.gov/search/map/mars_mgs_mola_dem_463m) (Mars Global Surveyor), 463 m | 3D terrain of Mars | NASA, USGS Astrogeology | Public domain |
| [LOLA](https://astrogeology.usgs.gov/search/map/moon_lro_lola_dem_118m) (Lunar Reconnaissance Orbiter), 118 m | 3D terrain of the Moon | NASA, USGS Astrogeology | Public domain |
| [Copernicus DEM GLO-90](https://registry.opendata.aws/copernicus-dem/) | 3D terrain of the Earth | ESA, Copernicus programme (AWS Open Data) | Free use with attribution |
| [NASA Mars Trek](https://trek.nasa.gov/mars/) (Viking color mosaic) | 3D view imagery, Mars | NASA | Public domain |
| [NASA Moon Trek](https://trek.nasa.gov/moon/) (LRO WAC mosaic) | 3D view imagery, Moon | NASA | Public domain |
| [Esri World Imagery](https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9) | 3D view imagery, Earth | Esri, Maxar, Earthstar Geographics | Esri terms of use, attribution shown |
| Literature on known analogs (Haughton-Mars Project, Navarro-González et al. 2003, Doran et al. 2010, Fernández-Remolar et al. 2005, Horgan et al. 2020, AMASE expeditions, ESA PANGAEA training, Mars Society MDRS) | Known analogs returned with each search | Cited in `services/known_analogs.py` | Citation |
