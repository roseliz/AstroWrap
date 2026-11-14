"""Rock classes shared by the three bodies, and the geologic map units assigned to each of them.

The script prints the units of a map that it cannot classify: add them to MAP_UNITS.
"""

from __future__ import annotations

# Fixed order: it is the order of the lithology vector
ROCK_CLASSES = ["basalte", "volcanique_felsique", "pyroclastique", "plutonique_basique", "plutonique_felsique",
                "sedimentaire_clastique", "non_consolide", "carbonate", "evaporite", "metamorphique", "glace", "impact"]

MAP_UNITS = {
    # GLiM first-level lithological classes (Hartmann and Moosdorf 2012)
    "earth": {
        "su": "non_consolide",           # unconsolidated sediments (alluvium, eolian sand)
        "ss": "sedimentaire_clastique",  # siliciclastic sedimentary rocks
        "sm": "sedimentaire_clastique",  # mixed sedimentary rocks
        "sc": "carbonate",               # carbonate sedimentary rocks
        "ev": "evaporite",               # evaporites
        "py": "pyroclastique",           # pyroclastics
        "vb": "basalte",                 # basic volcanic rocks
        "vi": "volcanique_felsique",     # intermediate volcanic rocks
        "va": "volcanique_felsique",     # acid volcanic rocks
        "pb": "plutonique_basique",      # basic plutonic rocks (gabbro, anorthosite)
        "pi": "plutonique_felsique",     # intermediate plutonic rocks
        "pa": "plutonique_felsique",     # acid plutonic rocks
        "mt": "metamorphique",           # metamorphic rocks
        "ig": "glace",                   # ice and glaciers
    },
    # USGS SIM 3292 global geologic map units (Tanaka et al. 2014)
    "mars": {
        # volcanic units and edifices
        "Av": "basalte", "AHv": "basalte", "Ave": "basalte", "lAv": "basalte", "lAvf": "basalte",
        "eHv": "basalte", "lHv": "basalte", "lHvf": "basalte", "Hve": "basalte", "lNv": "basalte",
        "Nve": "basalte", "Nhe": "basalte",
        # impact unit and Noachian highlands (ancient cratered crust, breccias, impact basin massifs)
        "AHi": "impact", "eNh": "impact", "eNhm": "impact", "mNh": "impact", "mNhm": "impact", "lNh": "impact",
        "HNhu": "impact", "Nhu": "impact", "eHh": "impact",
        # basin fills, transition units (including outflow channels), northern lowlands, Hesperian polar units
        "eAb": "sedimentaire_clastique", "eHb": "sedimentaire_clastique", "HNb": "sedimentaire_clastique",
        "lHb": "sedimentaire_clastique", "AHtu": "sedimentaire_clastique", "eHt": "sedimentaire_clastique",
        "HNt": "sedimentaire_clastique", "Ht": "sedimentaire_clastique", "Hto": "sedimentaire_clastique",
        "Htu": "sedimentaire_clastique", "lHt": "sedimentaire_clastique", "lHl": "sedimentaire_clastique",
        "mAl": "sedimentaire_clastique", "Hp": "sedimentaire_clastique", "Hpe": "sedimentaire_clastique",
        "Hpu": "sedimentaire_clastique",
        # debris aprons and polar dunes
        "Aa": "non_consolide", "ANa": "non_consolide", "lAa": "non_consolide", "lApd": "non_consolide",
        # polar layered deposits and polar cap
        "Ap": "glace", "Apu": "glace", "lApc": "glace",
    },
    # USGS Unified Geologic Map of the Moon (2020), GeoUnits
    "moon": {
        # maria and volcanic domes
        "Mare Unit": "basalte", "Upper Mare Unit": "basalte", "Lower Mare Unit": "basalte",
        "Mare Dome Unit": "basalte",
        # dark mantling deposits
        "Dark Mantling Unit": "pyroclastique",
        # highlands (anorthositic crust)
        "Terra Unit": "plutonique_basique", "Plains and Mantling, Terra Unit": "plutonique_basique",
        "Terra Dome Unit": "plutonique_basique", "Plateau Unit": "plutonique_basique",
        # craters, basins, light plains (basin ejecta), Orientale, Imbrium and Nectaris formations
        "Crater Unit": "impact", "Upper Crater Unit": "impact", "Lower Crater Unit": "impact",
        "Crater Undivided Unit": "impact", "Crater Cluster Unit": "impact", "Secondary Crater Unit": "impact",
        "Crater Fracture Floor Unit": "impact", "Imbrium Crater Unit": "impact",
        "Basin Undivided Unit": "impact", "Basin Lineated Unit": "impact", "Basin Secondary Crater Unit": "impact",
        "Basin Massif Unit": "impact", "Grooved Terrain Unit": "impact", "Plains Unit": "impact",
        "Orientale Hevelius Formation, Secondary Crater Facies Unit": "impact",
        "Orientale Hevelius Formation, Inner Facies Unit": "impact",
        "Orientale Montes Rook Formation, Knobby Facies Unit": "impact",
        "Orientale Montes Rook Formation, Massif Facies Unit": "impact",
        "Orientale Maunder Formation Unit": "impact", "Imbrium Alpes Formation Unit": "impact",
        "Imbrium Fra Mauro Formation Unit": "impact", "Imbrium Apenninus Formation Unit": "impact",
        "Nectaris Janssen Formation Unit": "impact",
    },
}


def class_ranks(body: str) -> dict[str, int]:
    """Map unit code -> rank of its rock class in ROCK_CLASSES, for one body."""
    return {unit: ROCK_CLASSES.index(rock) for unit, rock in MAP_UNITS[body].items()}
