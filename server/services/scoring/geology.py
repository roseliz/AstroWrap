"""Rocks (geology_mineralogy module): only the lithology enters the score.

The minerals (comp_*, part_oxyde_fer) stay in the Parquet files but are not compared. On Mars, OMEGA only gives
pyroxene and olivine, which EMIT does not see on the Earth: the comparison was dropped for every area of Mars and
of the Moon. It can come back with the clays, sulfates and carbonates of Mars (MOCAAS database, Carter et al. 2023).
"""

from .base import ModuleScore, Variable

# Rock classes, as named in the module's columns (litho_<class>)
LITHOLOGY = ["basalte", "volcanique_felsique", "pyroclastique", "plutonique_basique", "plutonique_felsique",
             "sedimentaire_clastique", "non_consolide", "carbonate", "evaporite", "metamorphique", "glace", "impact"]


class Geology(ModuleScore):
    key = "geology"
    name = "Rocks"
    folder = "geology_mineralogy"
    reliability = ("geology_mineralogy", "couverture_lithologie")   # the module's "fiabilite" mixes in the mineral coverage
    variables = [
        Variable("lithology", "Rock types", "hellinger", "geology_mineralogy", [f"litho_{c}" for c in LITHOLOGY],
                 classes=LITHOLOGY),
    ]
