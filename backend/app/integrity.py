"""Signed release-manifest verification for runtime SQLite databases."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import base64
import binascii
import json
from pathlib import Path
import sqlite3

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from .config import ROOT, settings
from .review import CLINICALLY_REVIEWED_STATUS


MANIFEST_VERSION = 1
DATABASE_SCHEMA_VERSION = 1
REQUIRED_DATABASES = {
    "runtime": settings.database_path,
    "top20": settings.top20_database_path,
}


@dataclass(frozen=True)
class IntegrityResult:
    ok: bool
    reason: str
    manifest_id: str | None = None
    expires_at: str | None = None


def canonical_json(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_facts(path: Path) -> tuple[int, dict[str, str]]:
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"SQLite integrity_check failed: {integrity}")
        schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
    return schema_version, metadata


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed.astimezone(timezone.utc)


def _verify_approval(entry: dict[str, object]) -> None:
    if entry.get("review_status") != CLINICALLY_REVIEWED_STATUS:
        return
    for key in ("reviewer", "reviewed_at", "approval_id"):
        if not isinstance(entry.get(key), str) or not str(entry[key]).strip():
            raise ValueError(f"clinically reviewed database lacks {key}")
    _parse_utc(str(entry["reviewed_at"]))


def manifest_database_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError as error:
        raise ValueError(f"database path is outside the application root: {path}") from error


def verify_release_manifest(
    manifest_path: Path | None = None,
    signature_path: Path | None = None,
    public_key_path: Path | None = None,
    databases: dict[str, Path] | None = None,
    now: datetime | None = None,
) -> IntegrityResult:
    manifest_file = manifest_path or settings.release_manifest_path
    signature_file = signature_path or settings.release_signature_path
    key_file = public_key_path or settings.release_public_key_path
    expected_databases = databases or REQUIRED_DATABASES
    try:
        manifest = json.loads(manifest_file.read_bytes())
        if not isinstance(manifest, dict):
            raise ValueError("release manifest must be a JSON object")
        signature = base64.b64decode(signature_file.read_text(encoding="ascii").strip(), validate=True)
        public_key = load_pem_public_key(key_file.read_bytes())
        if not isinstance(public_key, Ed25519PublicKey):
            raise ValueError("release public key must be Ed25519")
        public_key.verify(signature, canonical_json(manifest))
        if manifest.get("manifest_version") != MANIFEST_VERSION:
            raise ValueError("unsupported manifest version")
        manifest_id = manifest.get("manifest_id")
        expires_at = manifest.get("expires_at")
        if not isinstance(manifest_id, str) or not manifest_id:
            raise ValueError("manifest_id is required")
        if not isinstance(expires_at, str):
            raise ValueError("expires_at is required")
        if (now or datetime.now(timezone.utc)) > _parse_utc(expires_at):
            raise ValueError("release manifest has expired")
        entries = manifest.get("databases")
        if not isinstance(entries, dict):
            raise ValueError("database entries are required")
        for name, expected_path in expected_databases.items():
            entry = entries.get(name)
            if not isinstance(entry, dict):
                raise ValueError(f"database entry is missing: {name}")
            if entry.get("path") != manifest_database_path(expected_path):
                raise ValueError(f"database path mismatch: {name}")
            _verify_approval(entry)
            if not expected_path.is_file():
                raise ValueError(f"database file is missing: {name}")
            if entry.get("sha256") != file_sha256(expected_path):
                raise ValueError(f"database hash mismatch: {name}")
            schema_version, metadata = sqlite_facts(expected_path)
            if schema_version != DATABASE_SCHEMA_VERSION:
                raise ValueError(f"unsupported database schema version: {name}")
            if entry.get("schema_version") != schema_version:
                raise ValueError(f"schema version mismatch: {name}")
            if entry.get("review_status") != metadata.get("review_status"):
                raise ValueError(f"review status mismatch: {name}")
            date_key = "updated_at" if name == "runtime" else "dataset_date"
            if entry.get("dataset_date") != metadata.get(date_key):
                raise ValueError(f"dataset date mismatch: {name}")
        return IntegrityResult(True, "ok", manifest_id=manifest_id, expires_at=expires_at)
    except InvalidSignature:
        return IntegrityResult(False, "release manifest signature is invalid")
    except FileNotFoundError:
        return IntegrityResult(False, "release integrity file is missing")
    except PermissionError:
        return IntegrityResult(False, "release integrity file is unreadable")
    except json.JSONDecodeError:
        return IntegrityResult(False, "release manifest JSON is invalid")
    except binascii.Error:
        return IntegrityResult(False, "release manifest signature encoding is invalid")
    except OSError:
        return IntegrityResult(False, "release integrity verification could not read a file")
    except (ValueError, TypeError, KeyError) as error:
        return IntegrityResult(False, str(error))
