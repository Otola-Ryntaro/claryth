"""Release-manifest signature and database-integrity tests."""

from __future__ import annotations

import base64
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import sqlite3
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.app.integrity import (
    MANIFEST_VERSION,
    canonical_json,
    file_sha256,
    manifest_database_path,
    sqlite_facts,
    verify_release_manifest,
)


def make_database(path: Path, *, schema_version: int = 1, reviewed: bool = False) -> None:
    review_status = "clinically_reviewed" if reviewed else "review_required"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("CREATE TABLE payload (value TEXT NOT NULL)")
        connection.execute("INSERT INTO payload(value) VALUES ('signed data')")
        connection.execute(f"PRAGMA user_version = {schema_version}")
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            [("review_status", review_status), ("updated_at", "2026-06-13"), ("dataset_date", "2026-06-13")],
        )
        connection.commit()


def database_entry(path: Path, date_key: str, *, include_approval: bool) -> dict[str, object]:
    schema_version, metadata = sqlite_facts(path)
    return {
        "path": manifest_database_path(path),
        "sha256": file_sha256(path),
        "schema_version": schema_version,
        "dataset_date": metadata[date_key],
        "review_status": metadata["review_status"],
        "reviewer": "release-reviewer" if include_approval else None,
        "reviewed_at": "2026-06-13T00:00:00+00:00" if include_approval else None,
        "approval_id": "APR-2026-001" if include_approval else None,
    }


def signed_fixture(
    *,
    reviewed: bool = False,
    schema_version: int = 1,
    expires_delta: timedelta = timedelta(days=1),
) -> tuple[Path, dict[str, Path]]:
    directory = Path("tests") / f".integrity-{uuid4().hex}"
    directory.mkdir()
    runtime = directory / "runtime.sqlite"
    top20 = directory / "top20.sqlite"
    make_database(runtime, reviewed=reviewed, schema_version=schema_version)
    make_database(top20, reviewed=reviewed, schema_version=schema_version)
    private_key = Ed25519PrivateKey.generate()
    public_key = directory / "public.pem"
    public_key.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "manifest_id": "test-release",
        "created_at": "2026-06-13T00:00:00+00:00",
        "expires_at": (datetime.now(timezone.utc) + expires_delta).isoformat(),
        "databases": {
            "runtime": database_entry(runtime, "updated_at", include_approval=reviewed),
            "top20": database_entry(top20, "dataset_date", include_approval=reviewed),
        },
    }
    manifest_path = directory / "manifest.json"
    signature_path = directory / "manifest.sig"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    signature_path.write_text(
        base64.b64encode(private_key.sign(canonical_json(manifest))).decode("ascii"),
        encoding="ascii",
    )
    return directory, {
        "runtime": runtime,
        "top20": top20,
        "manifest": manifest_path,
        "signature": signature_path,
        "public_key": public_key,
    }


def verify(paths: dict[str, Path]):
    return verify_release_manifest(
        manifest_path=paths["manifest"],
        signature_path=paths["signature"],
        public_key_path=paths["public_key"],
        databases={"runtime": paths["runtime"], "top20": paths["top20"]},
    )


def test_valid_signed_manifest_is_accepted() -> None:
    directory, paths = signed_fixture(reviewed=True)
    try:
        result = verify(paths)
        assert result.ok is True
        assert result.manifest_id == "test-release"
    finally:
        shutil.rmtree(directory)


def test_database_byte_change_is_rejected() -> None:
    directory, paths = signed_fixture()
    try:
        with paths["runtime"].open("ab") as stream:
            stream.write(b"changed")
        result = verify(paths)
        assert result.ok is False
        assert "hash mismatch" in result.reason
    finally:
        shutil.rmtree(directory)


def test_missing_database_is_rejected() -> None:
    directory, paths = signed_fixture()
    try:
        paths["top20"].unlink()
        result = verify(paths)
        assert result.ok is False
        assert "file is missing" in result.reason
    finally:
        shutil.rmtree(directory)


def test_old_schema_version_is_rejected() -> None:
    directory, paths = signed_fixture(schema_version=0)
    try:
        result = verify(paths)
        assert result.ok is False
        assert "unsupported database schema version" in result.reason
    finally:
        shutil.rmtree(directory)


def test_invalid_signature_is_rejected() -> None:
    directory, paths = signed_fixture()
    try:
        paths["signature"].write_text(base64.b64encode(b"x" * 64).decode("ascii"), encoding="ascii")
        result = verify(paths)
        assert result.ok is False
        assert "signature is invalid" in result.reason
    finally:
        shutil.rmtree(directory)


def test_expired_manifest_is_rejected() -> None:
    directory, paths = signed_fixture(expires_delta=timedelta(days=-1))
    try:
        result = verify(paths)
        assert result.ok is False
        assert "expired" in result.reason
    finally:
        shutil.rmtree(directory)


def test_reviewed_database_without_approval_metadata_is_rejected() -> None:
    directory, paths = signed_fixture(reviewed=True)
    try:
        manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
        manifest["databases"]["runtime"]["approval_id"] = None
        private_key = Ed25519PrivateKey.generate()
        paths["public_key"].write_bytes(
            private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        paths["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
        paths["signature"].write_text(
            base64.b64encode(private_key.sign(canonical_json(manifest))).decode("ascii"),
            encoding="ascii",
        )
        result = verify(paths)
        assert result.ok is False
        assert "approval_id" in result.reason
    finally:
        shutil.rmtree(directory)
