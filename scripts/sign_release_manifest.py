"""Create and sign a release manifest for the runtime databases."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from uuid import uuid4

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import settings
from backend.app.integrity import (
    MANIFEST_VERSION,
    canonical_json,
    file_sha256,
    manifest_database_path,
    sqlite_facts,
)
from backend.app.review import CLINICALLY_REVIEWED_STATUS


def approval_value(cli_value: str | None, metadata: dict[str, str], key: str) -> str | None:
    value = cli_value or metadata.get(key)
    return value.strip() if value and value.strip() else None


def database_entry(path: Path, prefix: str, args: argparse.Namespace) -> dict[str, object]:
    schema_version, metadata = sqlite_facts(path)
    review_status = metadata.get("review_status")
    reviewer = approval_value(getattr(args, f"{prefix}_reviewer"), metadata, "reviewer")
    reviewed_at = approval_value(getattr(args, f"{prefix}_reviewed_at"), metadata, "reviewed_at")
    approval_id = approval_value(getattr(args, f"{prefix}_approval_id"), metadata, "approval_id")
    if review_status == CLINICALLY_REVIEWED_STATUS and not all(
        (reviewer, reviewed_at, approval_id)
    ):
        raise ValueError(f"{prefix} is clinically reviewed but approval metadata is incomplete")
    date_key = "updated_at" if prefix == "runtime" else "dataset_date"
    return {
        "path": manifest_database_path(path),
        "sha256": file_sha256(path),
        "schema_version": schema_version,
        "dataset_date": metadata.get(date_key),
        "review_status": review_status,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "approval_id": approval_id,
    }


def add_approval_arguments(parser: argparse.ArgumentParser, prefix: str) -> None:
    parser.add_argument(f"--{prefix}-reviewer")
    parser.add_argument(f"--{prefix}-reviewed-at")
    parser.add_argument(f"--{prefix}-approval-id")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-key", type=Path, default=ROOT / ".runtime" / "release_private_key.pem")
    parser.add_argument("--manifest", type=Path, default=settings.release_manifest_path)
    parser.add_argument("--signature", type=Path, default=settings.release_signature_path)
    parser.add_argument("--runtime-db", type=Path, default=settings.database_path)
    parser.add_argument("--top20-db", type=Path, default=settings.top20_database_path)
    parser.add_argument("--manifest-id", default=f"release-{uuid4()}")
    parser.add_argument("--expires-at", required=True, help="Timezone-aware ISO 8601 timestamp")
    add_approval_arguments(parser, "runtime")
    add_approval_arguments(parser, "top20")
    args = parser.parse_args()

    expires_at = datetime.fromisoformat(args.expires_at.replace("Z", "+00:00"))
    if expires_at.tzinfo is None:
        parser.error("--expires-at must include a timezone")
    if expires_at.astimezone(timezone.utc) <= datetime.now(timezone.utc):
        parser.error("--expires-at must be in the future")

    private_key = load_pem_private_key(args.private_key.read_bytes(), password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        parser.error("--private-key must contain an Ed25519 private key")
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "manifest_id": args.manifest_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "expires_at": expires_at.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "databases": {
            "runtime": database_entry(args.runtime_db, "runtime", args),
            "top20": database_entry(args.top20_db, "top20", args),
        },
    }
    signature = private_key.sign(canonical_json(manifest))
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.signature.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.signature.write_text(base64.b64encode(signature).decode("ascii") + "\n", encoding="ascii")
    print(f"manifest: {args.manifest}")
    print(f"signature: {args.signature}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
