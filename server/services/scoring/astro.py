"""Caves and habitability (astrobiology_habitability_caves module).

Object counts are compared by their rank within the body: the H3 cells of one body have similar areas, and an
Earth cell (253 km²) is 3.5 times larger than a Mars cell (72 km²).
"""

from .base import ModuleScore, Variable


class Astro(ModuleScore):
    key = "astro"
    name = "Caves and habitability"
    folder = "astrobiology_habitability_caves"
    reliability = ("astrobiology_habitability_caves", "fiabilite")
    variables = [
        Variable("part_karst", "Karst share", "abs", "astrobiology_habitability_caves", ["part_karst"]),
        Variable("caves", "Caves and pits (rank within the body)", "rank", "astrobiology_habitability_caves", ["n_cavites"]),
        Variable("lava_tubes", "Lava tubes (rank within the body)", "rank", "astrobiology_habitability_caves",
                 ["n_tubes_lave"]),
        Variable("volcanoes", "Volcanoes (rank within the body)", "rank", "astrobiology_habitability_caves", ["n_volcans"]),
    ]
