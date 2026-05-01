"""Environment alias helpers for deployment/runtime target selection."""

from __future__ import annotations

from collections.abc import Iterable

_ENVIRONMENT_ALIASES: dict[str, tuple[str, ...]] = {
    "dev": ("dev", "development"),
    "staging": ("staging", "stage"),
    "production": ("production", "prod"),
}

_ENVIRONMENT_CANONICAL: dict[str, str] = {
    alias: canonical for canonical, aliases in _ENVIRONMENT_ALIASES.items() for alias in aliases
}


def normalize_deployment_environment(value: object) -> str | None:
    """Return the canonical CP deployment environment label.

    Control Plane APIs historically use ``production`` while gateway inventory
    often stores the shorter ``prod`` label. Runtime selection must treat both
    as the same environment.
    """
    if value is None:
        return None
    env = str(value).strip().lower()
    if not env:
        return None
    return _ENVIRONMENT_CANONICAL.get(env, env)


def deployment_environment_aliases(value: object) -> tuple[str, ...]:
    """Return accepted storage aliases for an environment filter."""
    canonical = normalize_deployment_environment(value)
    if canonical is None:
        return ()
    return _ENVIRONMENT_ALIASES.get(canonical, (canonical,))


def deployment_environment_matches(left: object, right: object) -> bool:
    """Return True when two environment labels identify the same target env."""
    return normalize_deployment_environment(left) == normalize_deployment_environment(right)


def unique_environment_aliases(values: Iterable[object]) -> tuple[str, ...]:
    """Return unique aliases for several environment labels, preserving order."""
    seen: set[str] = set()
    aliases: list[str] = []
    for value in values:
        for alias in deployment_environment_aliases(value):
            if alias not in seen:
                seen.add(alias)
                aliases.append(alias)
    return tuple(aliases)
