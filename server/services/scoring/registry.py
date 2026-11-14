"""Active modules, in the default order of the funnel."""

from .thermal import Thermal
from .topography import Topography
from .wind import Wind

MODULES = [Topography(), Thermal(), Wind()]
BY_KEY = {m.key: m for m in MODULES}


def for_body(body: str, requested=None) -> list:
    """Modules with data for this body (and the Earth), restricted to `requested` if given."""
    return [m for m in MODULES if (requested is None or m.key in requested) and m.available(body)
            and m.available("earth")]
