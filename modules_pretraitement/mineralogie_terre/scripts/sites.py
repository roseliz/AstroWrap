"""Reference zones and sites, with their sources.

CALIBRATION_ZONES   areas whose granules are processed to check the thresholds (calibration_list.py)
CALIBRATION_SITES   expected presence / absence of a family, used to check the thresholds (calibration.py)
AUDIT_SITES         independent reference sites, never used for calibration, checked on the final table
                    (merge.py)
"""

from __future__ import annotations

import pandas as pd

# (name, west, south, east, north, description)
# The zones_emit list of geology_mineralogy, plus reference sites.
CALIBRATION_ZONES = [
    ("atacama", -70.5, -25.5, -68.5, -23.5, "Atacama Desert: hyperarid soils, salts, Mars analogue"),
    ("death_valley", -117.5, 35.5, -115.5, 37.0, "Death Valley and Mojave: evaporites, alluvial fans"),
    ("rio_tinto", -6.75, 37.55, -6.45, 37.80,
     "Rio Tinto: mines and upper river, acidic iron sulfates and oxides (jarosite), Meridiani analogue; "
     "many scenes, the least cloudy ones"),
    ("rio_tinto_aval", -7.0, 37.2, -6.4, 37.6, "Lower Rio Tinto and Iberian Pyrite Belt (Tharsis)"),
    ("utah_mdrs", -111.3, 38.0, -110.3, 39.0,
     "Hanksville and San Rafael Swell (Mars Desert Research Station): clays, sandstones"),
    ("pilbara", 118.5, -22.0, 120.5, -20.5, "Pilbara: Archean basalts and cherts"),
    ("namib", 14.5, -25.5, 16.0, -23.5, "Namib: sand, gypsum"),
    ("hoggar", 5.0, 22.5, 6.5, 23.8, "Hoggar: Saharan basalts and volcanoes"),
    ("mauna_kea", -156.0, 19.3, -155.0, 20.1, "Mauna Kea: weathered basalts and tephra, lunar and Martian analogue"),
    ("qaidam", 92.0, 37.5, 94.0, 38.5, "Qaidam Basin: evaporites and yardangs, Mars analogue"),
    ("lanzarote", -14.0, 28.8, -13.4, 29.3, "Lanzarote: recent basaltic lava flows"),
    ("danakil", 40.0, 14.0, 40.6, 14.5, "Danakil Depression (Dallol): salts, sulfates, hydrothermal activity"),
    ("pinacate", -114.0, 31.6, -113.2, 32.1, "El Pinacate: basaltic volcanic field and maars"),
    ("white_sands", -106.6, 32.6, -106.1, 33.1,
     "White Sands: gypsum dunes, analogue of the sulfate dunes of Olympia Undae"),
    ("lacs_acides_australie", 121.0, -33.0, 122.0, -32.3,
     "Acid saline lakes of Western Australia: jarosite, Meridiani analogue (Benison and Bowen 2006)"),
    ("salar_uyuni", -68.2, -20.6, -67.0, -19.8, "Salar de Uyuni: salt crust, analogue of the Martian chloride deposits"),
    ("meteor_crater", -111.2, 34.9, -110.9, 35.15, "Meteor Crater: simple impact crater and its ejecta"),
    ("lonar", 76.4, 19.9, 76.6, 20.05, "Lonar Crater: impact in the Deccan basalts, Martian crater analogue"),
    ("wadi_rum", 35.2, 29.4, 35.7, 29.8, "Wadi Rum: sandstones and rocky desert, Martian terrain analogue"),
    ("cuprite", -117.30, 37.45, -117.10, 37.60,
     "Cuprite (Nevada): hyperspectral imaging reference site, kaolinite, alunite, muscovite, calcite "
     "(Swayze et al. 2014)"),
    ("grand_erg_oriental", 7.5, 30.0, 8.5, 30.8,
     "Grand Erg Oriental: quartz dunes, negative reference for clays, carbonates and sulfates"),
    ("simpson", 136.5, -25.5, 137.5, -24.8, "Simpson Desert: red dunes, iron oxide coatings"),
]

# Calibration reference sites (phase 1). expected: "present" = the family must be detected on a notable
# fraction of the valid pixels; "absent" = it must almost never be (a detection is a false alarm).
# Location: either a small box (west, south, east, north) well inside the object, converted into H3 cells
# of resolution 7 (~5 km2), or a whole zone of CALIBRATION_ZONES.
# Published coordinates are only known to within 1 or 2 km: the boxes stay away from the edges.
# An "absent" site is only useful where Tetracorder produces low-confidence matches: a halite crust
# (no absorption band) constrains nothing (Salar de Uyuni: 0 % even without any filter).
# Grand Erg Oriental: no "absent" site for argile_al or mica, because Saharan sands carry kaolinite and
# illite coatings (Caquineau et al. 2002; EMIT L3 maps).
# The audit sites (AUDIT_SITES: Meteor Crater, Wadi Rum, Hoggar) are NOT used here.
_WHITE_SANDS = ("White Sands (dune core)", None, -106.32, 32.78, -106.24, 32.88)
_CUPRITE = ("Cuprite (hydrothermal centers)", None, -117.25, 37.50, -117.15, 37.56)
_TIMANFAYA = ("Timanfaya (1730-1736 lavas)", None, -13.80, 28.99, -13.73, 29.04)
_PINACATE = ("Pinacate (lavas)", None, -113.60, 31.70, -113.40, 31.85)
_RIO_TINTO = ("Rio Tinto (mines)", None, -6.62, 37.68, -6.56, 37.72)
_PILBARA = ("Pilbara", "pilbara", None, None, None, None)
_SIMPSON = ("Simpson Desert", "simpson", None, None, None, None)
_GRAND_ERG = ("Grand Erg Oriental", "grand_erg_oriental", None, None, None, None)
# (site, zone, west, south, east, north, family, expected, source)
CALIBRATION_SITES = [
    (*_WHITE_SANDS, "sulfate", "present", "gypsum dune field (NPS; Fryberger 2001)"),
    (*_WHITE_SANDS, "oxyde_fer", "absent", "almost pure gypsum"),
    (*_WHITE_SANDS, "carbonate", "absent", "almost pure gypsum"),
    (*_WHITE_SANDS, "argile_al", "absent", "almost pure gypsum"),
    (*_WHITE_SANDS, "argile_fe_mg", "absent", "almost pure gypsum"),
    (*_WHITE_SANDS, "mica", "absent", "almost pure gypsum"),
    (*_CUPRITE, "argile_al", "present", "kaolinite, halloysite, dickite around the alunite cores (Swayze et al. 2014)"),
    (*_CUPRITE, "mica", "present", "sericite at the edges of the centers (Swayze et al. 2014)"),
    (*_TIMANFAYA, "carbonate", "absent", "unaltered historical basaltic lava flows (Smithsonian GVP)"),
    (*_TIMANFAYA, "sulfate", "absent", "historical basaltic lava flows"),
    (*_TIMANFAYA, "argile_al", "absent", "historical basaltic lava flows"),
    (*_TIMANFAYA, "mica", "absent", "historical basaltic lava flows"),
    (*_PINACATE, "carbonate", "absent", "basaltic lava field and cones"),
    (*_PINACATE, "sulfate", "absent", "basaltic lava field and cones"),
    (*_RIO_TINTO, "oxyde_fer", "present", "gossans and spoil heaps with goethite and hematite (Fernández-Remolar et al. 2005)"),
    (*_PILBARA, "oxyde_fer", "present", "lateritic soils and ferruginous duricrusts"),
    (*_PILBARA, "sulfate", "absent", "no extensive evaporites"),
    (*_SIMPSON, "oxyde_fer", "present", "red dunes with hematite and goethite coatings"),
    (*_GRAND_ERG, "carbonate", "absent", "eolian quartz sand"),
    (*_GRAND_ERG, "sulfate", "absent", "eolian quartz sand"),
    (*_GRAND_ERG, "argile_fe_mg", "absent", "eolian quartz sand"),
]

# Independent reference sites: none of them was used to choose the thresholds. Ranges checked in phase 1 on
# the calibration granules (v002, SpecTf mask, r5 cell of the point): Meteor Crater medium carbonate 0.52;
# Wadi Rum argile_al 0.94, oxyde_fer 0.98, carbonate 0.005; Hoggar carbonate 0.001.
# (site, lat, lon, column, min, max, source)
AUDIT_SITES = [
    ("Meteor Crater", 35.027, -111.022, "det_carbonate_moyen", 0.3, 1.0,
     "limestone and dolomite ejecta of the Kaibab Formation (Shoemaker 1963)"),
    ("Meteor Crater", 35.027, -111.022, "det_sulfate_moyen", 0.0, 0.05, "no outcropping evaporites"),
    ("Wadi Rum", 29.575, 35.42, "det_oxyde_fer_moyen", 0.5, 1.0, "red Cambro-Ordovician sandstones"),
    ("Wadi Rum", 29.575, 35.42, "det_argile_al_moyen", 0.3, 1.0,
     "kaolinitic cement of the Disi and Umm Ishrin sandstones"),
    ("Wadi Rum", 29.575, 35.42, "det_carbonate_moyen", 0.0, 0.05, "siliceous sandstones"),
    ("Hoggar (Assekrem)", 23.27, 5.63, "det_carbonate_moyen", 0.0, 0.05, "Atakor basaltic plateau"),
    ("Hoggar (Assekrem)", 23.27, 5.63, "det_sulfate_moyen", 0.0, 0.05, "Atakor basaltic plateau"),
]


def zones_table() -> pd.DataFrame:
    """CALIBRATION_ZONES with the column names expected by the SQL queries."""
    return pd.DataFrame(CALIBRATION_ZONES, columns=["nom", "ouest", "sud", "est", "nord", "description"])


def calibration_sites_table() -> pd.DataFrame:
    """CALIBRATION_SITES with the column names expected by the SQL queries."""
    return pd.DataFrame(CALIBRATION_SITES,
                        columns=["site", "zone", "ouest", "sud", "est", "nord", "famille", "attendu", "source"])
