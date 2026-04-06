"""Small internal registry for domain-owned harness wiring."""

from __future__ import annotations

from .domains.base import DomainDefinition
from .domains.recommender import build_recommender_domain_definition

_DOMAIN_DEFINITIONS: dict[str, DomainDefinition] = {
    "recommender": build_recommender_domain_definition(),
}


def get_domain_definition(name: str = "recommender") -> DomainDefinition:
    """Return the registered internal domain definition by name."""
    try:
        return _DOMAIN_DEFINITIONS[name]
    except KeyError as exc:
        available = ", ".join(sorted(_DOMAIN_DEFINITIONS))
        raise ValueError(f"Unsupported domain `{name}`. Available domains: {available}.") from exc
