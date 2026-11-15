"""Water and ice (volatiles_hydrology_ice module)."""

from .base import ModuleScore, Variable


class Volatiles(ModuleScore):
    key = "volatiles"
    name = "Water and ice"
    folder = "volatiles_hydrology_ice"
    reliability = ("volatiles_hydrology_ice", "fiabilite")
    variables = [
        Variable("part_glace_surface", "Surface ice", "abs", "volatiles_hydrology_ice", ["part_glace_surface"]),
        Variable("indice_glace_sol", "Ground ice", "abs", "volatiles_hydrology_ice", ["indice_glace_sol"]),
        Variable("eau_sol_rang", "Soil water (rank within the body)", "abs", "volatiles_hydrology_ice", ["eau_sol_rang"]),
    ]
