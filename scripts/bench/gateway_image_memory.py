#!/usr/bin/env python3
"""Measure the pinned POC Envoy image locally; retain evidence, never pull or push."""

import json
import os
import platform
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

IMAGE = "envoyproxy/envoy@sha256:29d778ba078e0404d18fa45ffb834c062071b0f81dc0a6a41501ce8e23a0059f"
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(tempfile.mkdtemp(prefix="stoa-image-memory-"))
DEADLINE = time.monotonic() + 840


def run(args, **kwargs):
    return subprocess.run(args, check=True, timeout=max(1, DEADLINE - time.monotonic()), **kwargs)


def main():
    name = "stoa-memory-" + uuid.uuid4().hex[:12]
    evidence = {"status": "results pending", "image": IMAGE, "directory": str(OUT),
                "host": platform.platform(), "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        info = json.loads(run(["docker", "image", "inspect", IMAGE], capture_output=True).stdout)[0]
        evidence.update(image_id=info["Id"], platform="linux/" + info["Architecture"])
        evidence["source_sha"] = run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()
        run(["go", "test", "-c", "-o", str(OUT / "memory.test"), "./internal/xds"],
            cwd=ROOT / "stoa-go", env={**os.environ, "GOOS": "linux", "GOARCH": info["Architecture"],
                                     "CGO_ENABLED": "0", "GOPROXY": "off", "GOSUMDB": "off"})
        with (OUT / "test.log").open("w") as log:
            run(["docker", "run", "--name", name, "--network", "none", "--pull", "never",
                 "--mount", f"type=bind,src={OUT},dst=/evidence", "-e", "IMAGE_MEMORY=1",
                 "--entrypoint", "/evidence/memory.test", IMAGE,
                 "-test.run=^TestImageMemory$", "-test.v", "-test.timeout=10m"],
                stdout=log, stderr=subprocess.STDOUT)
        evidence.update(status="measured", results=json.loads((OUT / "results.json").read_text()))
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        evidence["error"] = str(exc)
    finally:
        try:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            pass
        (OUT / "run.json").write_text(json.dumps(evidence, indent=2) + "\n")
        print(json.dumps(evidence, indent=2))
    return 0 if evidence["status"] == "measured" else 1


if __name__ == "__main__":
    sys.exit(main())
