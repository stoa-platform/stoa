"""Local-only Helm invocation shared by the API render contracts."""

import shutil
import subprocess
from pathlib import Path

CHART = Path(__file__).resolve().parents[2] / "charts/stoa-platform"


def render(*arguments: str):
    executable = shutil.which("helm")
    if not executable:
        raise RuntimeError("Helm is required to run the render contracts.")
    return subprocess.run(
        [executable, "template", "installation", str(CHART), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
