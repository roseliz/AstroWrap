"""Wind and dust (wind_erosion_atmosphere module; no atmosphere on the Moon)."""

from .base import ModuleScore, Variable


class Wind(ModuleScore):
    key = "wind"
    name = "Wind and dust"
    folder = "wind_erosion_atmosphere"
    bodies = ("earth", "mars")
    reliability = ("wind_erosion_atmosphere", "fiabilite")
    variables = [
        Variable("vent_fort_rel", "Strong winds (rank within the body)", "rank", "wind_erosion_atmosphere", ["vent_fort_rel"],
                 raw_unit="× sand threshold"),
        Variable("part_dunes", "Dune share", "abs", "wind_erosion_atmosphere", ["part_dunes"]),
        Variable("part_sol_nu", "Bare ground share", "abs", "wind_erosion_atmosphere", ["part_sol_nu"]),
        Variable("poussiere_rang", "Dust (rank within the body)", "abs", "wind_erosion_atmosphere", ["poussiere_rang"]),
        Variable("tempetes_rang", "Dust storms (rank within the body)", "abs", "wind_erosion_atmosphere",
                 ["tempetes_rang"]),
    ]
