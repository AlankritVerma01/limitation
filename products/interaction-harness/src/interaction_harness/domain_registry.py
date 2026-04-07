"""Small internal registry for domain-owned harness wiring.

This registry is intentionally code-defined and in-repo. It is not a plugin
marketplace. The shared harness stays small by routing execution through one
registered domain definition at a time.
"""

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


def register_domain_definition(definition: DomainDefinition) -> None:
    """Register or replace one in-repo domain definition."""
    if definition.runner is None:
        raise ValueError(f"Domain `{definition.name}` must define a runner before registration.")
    _DOMAIN_DEFINITIONS[definition.name] = definition


def list_domain_definitions() -> tuple[str, ...]:
    """Return the sorted list of registered domain names."""
    return tuple(sorted(_DOMAIN_DEFINITIONS))


def list_public_domain_definitions() -> tuple[str, ...]:
    """Return the sorted list of public domain names exposed through the CLI."""
    return tuple(
        sorted(
            definition.name
            for definition in _DOMAIN_DEFINITIONS.values()
            if definition.public
        )
    )
