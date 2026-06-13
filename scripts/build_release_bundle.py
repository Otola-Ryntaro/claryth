"""Build a fixed, signed Clarith release archive without local credentials."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
from uuid import uuid4
import zipfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import settings
from backend.app.integrity import canonical_json, verify_release_manifest
from backend.app.review import CLINICALLY_REVIEWED_STATUS
from scripts.verify_release_bundle import sha256_bytes, verify_bundle
from top20_builder.review import verify_approved_golden_results


ROOT_FILES = ["README.md", "LICENSE", "pyproject.toml", "uv.lock"]
DATA_FILES = [
    "backend/data/seed.json",
    "backend/data/clarith.db",
    "backend/data/top20_interactions.sqlite",
    "backend/data/release_manifest.json",
    "backend/data/release_manifest.sig",
]
EXTENSION_FILES = [
    "extension/build.mjs",
    "extension/package.json",
    "extension/package-lock.json",
    "extension/tsconfig.json",
]
DOCUMENT_FILES = [
    "docs/user_guide.md",
    "docs/release_operations.md",
    "docs/release_checklist_template.md",
    "docs/e2e_test_record_template.md",
]
SCRIPT_FILES = [
    "scripts/clarith_launcher.ps1",
    "scripts/install_release.ps1",
    "scripts/install_windows_launcher.ps1",
    "scripts/uninstall_windows_launcher.ps1",
    "scripts/verify_release_bundle.py",
]


def iter_tree(relative: str, pattern: str = "*"):
    root = ROOT / relative
    for path in sorted(root.rglob(pattern)):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            yield path


def distribution_files(extra_files: list[Path] | None = None) -> list[Path]:
    files = [
        ROOT / path
        for path in ROOT_FILES + DATA_FILES + EXTENSION_FILES + DOCUMENT_FILES + SCRIPT_FILES
    ]
    files.extend(iter_tree("backend", "*.py"))
    files.extend(iter_tree("extension/src"))
    files.extend(iter_tree("artifacts/sbom", "*.cdx.json"))
    files.extend(extra_files or [])
    unique = sorted(set(files), key=lambda path: path.relative_to(ROOT).as_posix())
    missing = [path for path in unique if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"release input is missing: {missing[0]}")
    forbidden = [path for path in unique if ".runtime" in path.parts or path.name == "project-config.json"]
    if forbidden:
        raise ValueError(f"forbidden local file in release: {forbidden[0]}")
    return unique


def release_channel(data_manifest: dict[str, object], allow_evaluation: bool) -> str:
    entries = data_manifest.get("databases")
    if not isinstance(entries, dict):
        raise ValueError("data manifest database entries are missing")
    approved = True
    for entry in entries.values():
        if not isinstance(entry, dict):
            approved = False
            break
        approved = approved and entry.get("review_status") == CLINICALLY_REVIEWED_STATUS
        approved = approved and all(entry.get(key) for key in ("reviewer", "reviewed_at", "approval_id"))
    if approved:
        return "product"
    if allow_evaluation:
        return "evaluation"
    raise ValueError("product release requires clinically reviewed databases with approval metadata")


def write_deterministic_zip(archive_path: Path, files: list[Path]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            content = path.read_bytes()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            bundle.writestr(info, content)
            entries.append({"path": relative, "size": len(content), "sha256": sha256_bytes(content)})
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-id", default=f"{datetime.now():%Y%m%d}-{uuid4().hex[:8]}")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "release")
    parser.add_argument("--private-key", type=Path, default=ROOT / ".runtime" / "release_private_key.pem")
    parser.add_argument("--allow-evaluation", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    integrity = verify_release_manifest()
    if not integrity.ok:
        parser.error(f"data release integrity failed: {integrity.reason}")
    data_manifest = json.loads(settings.release_manifest_path.read_text(encoding="utf-8"))
    try:
        channel = release_channel(data_manifest, args.allow_evaluation)
    except ValueError as error:
        parser.error(str(error))
    private_key = load_pem_private_key(args.private_key.read_bytes(), password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        parser.error("release private key must be Ed25519")
    expected_public = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    if expected_public != settings.release_public_key_path.read_bytes():
        parser.error("release private key does not match the bundled public key")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"clarith-{channel}-{args.release_id}"
    archive_path = args.output_dir / f"{stem}.zip"
    manifest_path = args.output_dir / f"{stem}.manifest.json"
    signature_path = args.output_dir / f"{stem}.manifest.sig"
    public_key_path = args.output_dir / f"{stem}.public.pem"
    outputs = [archive_path, manifest_path, signature_path, public_key_path]
    if not args.force and any(path.exists() for path in outputs):
        parser.error("release output already exists; use --force to replace it")

    extra_files: list[Path] = []
    if channel == "product":
        approved_golden = ROOT / "artifacts" / "top20_promotion" / "golden_results.approved.json"
        try:
            verify_approved_golden_results(
                settings.top20_database_path, settings.seed_path, approved_golden
            )
        except (FileNotFoundError, ValueError) as error:
            parser.error(f"product release golden verification failed: {error}")
        extra_files.append(approved_golden)
    entries = write_deterministic_zip(archive_path, distribution_files(extra_files))
    archive_bytes = archive_path.read_bytes()
    manifest = {
        "manifest_version": 1,
        "release_id": args.release_id,
        "channel": channel,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_manifest_id": integrity.manifest_id,
        "archive": {
            "filename": archive_path.name,
            "size": len(archive_bytes),
            "sha256": hashlib.sha256(archive_bytes).hexdigest(),
        },
        "files": entries,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    signature_path.write_text(
        base64.b64encode(private_key.sign(canonical_json(manifest))).decode("ascii") + "\n",
        encoding="ascii",
    )
    shutil.copyfile(settings.release_public_key_path, public_key_path)
    verify_bundle(archive_path, manifest_path, signature_path, public_key_path)
    print(f"Built and verified {channel} release: {archive_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
