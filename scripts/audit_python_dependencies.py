"""Run pip-audit with only current, approved vulnerability exceptions."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from check_vulnerability_exceptions import validated_exceptions


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    executable = Path(sys.executable).with_name(
        "pip-audit.exe" if sys.platform == "win32" else "pip-audit"
    )
    if not executable.is_file():
        raise RuntimeError("pip-audit is not installed in the active Python environment")
    cache_dir = ROOT / ".runtime" / "pip-audit-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    command = [str(executable), "--strict", "--cache-dir", str(cache_dir)]
    for exception in validated_exceptions():
        if exception["ecosystem"] == "python":
            command.extend(["--ignore-vuln", exception["advisory"]])
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
