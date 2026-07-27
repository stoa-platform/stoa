"""Régression : CVE-2026-53539 — python-multipart, DoS via corps form-urlencoded.

Le Container Scan avait remonté `python-multipart==0.0.27` (HIGH, corrigé en
0.0.30). La régression à empêcher n'est pas un bug de notre code : c'est le
retour silencieux du pin vers une version vulnérable — par un rollback, une
résolution de conflit, ou une génération automatique de dépendances.

Le test porte donc sur le PIN DÉCLARÉ dans requirements.txt, qui est ce qui
détermine l'image construite. Il ne dépend d'aucun environnement installé et
échoue sur un `git revert` du correctif.
"""

import re
from pathlib import Path

import pytest

# Première version corrigée, telle que rapportée par l'avis amont et le scan.
FIRST_FIXED = (0, 0, 30)

REQUIREMENTS = Path(__file__).resolve().parents[1] / "requirements.txt"

_PIN_RE = re.compile(r"^python-multipart\s*==\s*([0-9][^\s;#]*)", re.IGNORECASE)


def _parse_version(raw: str) -> tuple[int, ...]:
    """`0.0.32` -> (0, 0, 32). Les suffixes non numériques sont ignorés."""
    parts: list[int] = []
    for chunk in raw.split("."):
        match = re.match(r"^(\d+)", chunk)
        if match is None:
            break
        parts.append(int(match.group(1)))
    if not parts:
        raise AssertionError(f"version python-multipart illisible : {raw!r}")
    return tuple(parts)


def _pinned_version() -> tuple[int, ...]:
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _PIN_RE.match(stripped)
        if match is not None:
            return _parse_version(match.group(1))
    raise AssertionError(
        "python-multipart n'est plus épinglé dans requirements.txt — "
        "la dépendance serait alors résolue librement, y compris vers une "
        "version vulnérable à CVE-2026-53539."
    )


def test_regression_cve_2026_53539_pin_is_not_vulnerable():
    """Le pin de requirements.txt doit rester >= 0.0.30 (correctif CVE-2026-53539)."""
    pinned = _pinned_version()
    assert pinned >= FIRST_FIXED, (
        f"python-multipart est épinglé en {'.'.join(map(str, pinned))}, "
        f"vulnérable à CVE-2026-53539 (DoS via corps form-urlencoded). "
        f"Corrigé à partir de {'.'.join(map(str, FIRST_FIXED))}."
    )


def test_regression_cve_2026_53539_installed_is_not_vulnerable():
    """Contrôle secondaire : la version réellement installée, si elle l'est."""
    metadata = pytest.importorskip("importlib.metadata")
    try:
        raw = metadata.version("python-multipart")
    except Exception:  # pragma: no cover - paquet absent de l'environnement
        pytest.skip("python-multipart n'est pas installé dans cet environnement")

    installed = _parse_version(raw)
    assert installed >= FIRST_FIXED, (
        f"python-multipart installé en {raw}, vulnérable à CVE-2026-53539. "
        f"Corrigé à partir de {'.'.join(map(str, FIRST_FIXED))}."
    )
