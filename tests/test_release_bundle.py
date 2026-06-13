"""Signed release archive and product-gate tests."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import shutil
from uuid import uuid4
import zipfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts.build_release_bundle import ROOT, distribution_files, release_channel
from scripts.verify_release_bundle import canonical_json, sha256_bytes, verify_bundle


def workspace() -> Path:
    path = Path("tests") / f".release-{uuid4().hex}"
    path.mkdir()
    return path


def signed_bundle(directory: Path) -> tuple[Path, Path, Path, Path]:
    archive = directory / "clarith-evaluation-test.zip"
    content = b"fixed release content"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("README.md", content)
    archive_bytes = archive.read_bytes()
    manifest = {
        "manifest_version": 1,
        "release_id": "test",
        "channel": "evaluation",
        "archive": {
            "filename": archive.name,
            "size": len(archive_bytes),
            "sha256": sha256_bytes(archive_bytes),
        },
        "files": [{"path": "README.md", "size": len(content), "sha256": sha256_bytes(content)}],
    }
    private_key = Ed25519PrivateKey.generate()
    public_key = directory / "public.pem"
    public_key.write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    manifest_path = directory / "manifest.json"
    signature_path = directory / "manifest.sig"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    signature_path.write_text(
        base64.b64encode(private_key.sign(canonical_json(manifest))).decode("ascii"),
        encoding="ascii",
    )
    return archive, manifest_path, signature_path, public_key


def test_signed_bundle_and_every_file_are_verified() -> None:
    directory = workspace()
    try:
        paths = signed_bundle(directory)
        manifest = verify_bundle(*paths)
        assert manifest["release_id"] == "test"
    finally:
        shutil.rmtree(directory)


def test_archive_tampering_is_rejected() -> None:
    directory = workspace()
    try:
        paths = signed_bundle(directory)
        with paths[0].open("ab") as stream:
            stream.write(b"tampered")
        with pytest.raises(ValueError, match="archive size|archive hash"):
            verify_bundle(*paths)
    finally:
        shutil.rmtree(directory)


def test_product_release_requires_review_and_approval_metadata() -> None:
    reviewed = {
        "databases": {
            "runtime": {
                "review_status": "clinically_reviewed",
                "reviewer": "reviewer",
                "reviewed_at": "2026-06-13T00:00:00+00:00",
                "approval_id": "APR-1",
            },
            "top20": {
                "review_status": "clinically_reviewed",
                "reviewer": "reviewer",
                "reviewed_at": "2026-06-13T00:00:00+00:00",
                "approval_id": "APR-2",
            },
        }
    }
    assert release_channel(reviewed, False) == "product"

    unreviewed = {"databases": {"runtime": {"review_status": "review_required"}}}
    with pytest.raises(ValueError, match="clinically reviewed"):
        release_channel(unreviewed, False)
    assert release_channel(unreviewed, True) == "evaluation"


def test_distribution_excludes_credentials_authoring_tools_and_source_material() -> None:
    names = {path.relative_to(ROOT).as_posix() for path in distribution_files()}
    forbidden_fragments = {
        ".runtime",
        "project-config.json",
        "release_private_key.pem",
        "generate_release_signing_key.py",
        "sign_release_manifest.py",
        "build_release_bundle.py",
        "note_article_draft.md",
        "top20_interactions.candidate.sqlite",
        "top20_review",
        "top20_promotion",
    }
    assert not any(fragment in name for name in names for fragment in forbidden_fragments)
    assert not any(Path(name).suffix.lower() in {".xml", ".pdf", ".csv"} for name in names)
    assert "scripts/install_release.ps1" in names
    assert "scripts/verify_release_bundle.py" in names
