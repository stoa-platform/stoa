"""Pytest configuration for scripts/ci tests.

Makes the sibling scripts/ci/ directory importable so tests can
`import map_score_to_label` etc. without packaging overhead.
"""

from __future__ import annotations

import sys
from pathlib import Path

_CI_DIR = Path(__file__).resolve().parent.parent
if str(_CI_DIR) not in sys.path:
    sys.path.insert(0, str(_CI_DIR))
