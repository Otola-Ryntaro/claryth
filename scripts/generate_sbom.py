"""Generate deterministic CycloneDX SBOMs from the locked Python and npm inputs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def executable(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None and sys.platform == "win32":
        resolved = shutil.which(f"{name}.exe") or shutil.which(f"{name}.cmd")
    if resolved is None:
        raise RuntimeError(f"required command is not installed: {name}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "sbom")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    python_output = args.output_dir / "python.cdx.json"
    uv_cache = ROOT / ".runtime" / "uv-cache"
    uv_cache.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "UV_CACHE_DIR": str(uv_cache)}
    subprocess.run(
        [
            executable("uv"),
            "export",
            "--preview-features",
            "sbom-export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--format",
            "cyclonedx1.5",
            "--output-file",
            str(python_output),
        ],
        cwd=ROOT,
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )

    npm_result = subprocess.run(
        [executable("npm"), "sbom", "--package-lock-only", "--sbom-format", "cyclonedx"],
        cwd=ROOT / "extension",
        check=True,
        capture_output=True,
        text=True,
    )
    npm_payload = json.loads(npm_result.stdout)
    (args.output_dir / "extension.cdx.json").write_text(
        json.dumps(npm_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Python SBOM: {python_output}")
    print(f"Extension SBOM: {args.output_dir / 'extension.cdx.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
