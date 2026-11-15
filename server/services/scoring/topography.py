"""Terrain (topography_morphometry module, 500 m baseline, the only one shared by the three bodies)."""

from .base import ModuleScore, Variable

DECILES = [f"pente_p{k}0" for k in range(1, 10)]     # slope deciles (column names of the module)


class Topography(ModuleScore):
    key = "topography"
    name = "Terrain"
    folder = "topography_morphometry"
    reliability = ("topography_morphometry", "fiabilite")
    suffixes = {"topography_morphometry": "_b500"}
    variables = [
        Variable("slopes", "Slope distribution (deciles)", "deciles", "topography_morphometry", DECILES, "°"),
        Variable("part_pente_inf_5", "Flat ground share (< 5°)", "abs", "topography_morphometry", ["part_pente_inf_5"]),
        Variable("rugosite_rms", "Roughness (rank within the body)", "rank", "topography_morphometry", ["rugosite_rms"],
                 raw_unit="m"),
        Variable("elevation_range", "Local elevation range (rank within the body)", "rank", "topography_morphometry",
                 ["denivele_p5_p95"], raw_unit="m"),
        Variable("densite_crateres", "Crater density (rank within the body)", "rank", "topography_morphometry",
                 ["densite_crateres"], raw_unit="per 1,000 km²"),
    ]
