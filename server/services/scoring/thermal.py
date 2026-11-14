"""Temperature and light (thermal_light_extrems module)."""

from .base import ModuleScore, Variable


class Thermal(ModuleScore):
    key = "thermal"
    name = "Temperature and light"
    folder = "thermal_light_extrems"
    reliability = ("thermal", "reliability")
    variables = [
        Variable("lst_day_mean", "Ground temperature, day", "abs", "thermal", ["lst_day_mean"], "K"),
        Variable("lst_night_mean", "Ground temperature, night", "abs", "thermal", ["lst_night_mean"], "K"),
        Variable("amplitude", "Day-night range", "abs", "thermal", ["lst_day_mean", "lst_night_mean"], "K",
                 compute="difference"),
        Variable("cold_fraction", "Share of very cold time (for the body)", "abs", "extremes", ["cold_fraction"]),
        Variable("hot_fraction", "Share of very hot time (for the body)", "abs", "extremes", ["hot_fraction"]),
        Variable("daylight_fraction_min", "Daylight share, darkest season", "abs", "illumination",
                 ["daylight_fraction_min"]),
        Variable("daylight_fraction_max", "Daylight share, brightest season", "abs", "illumination",
                 ["daylight_fraction_max"]),
    ]
