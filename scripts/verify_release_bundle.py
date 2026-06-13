"""Verify a signed Clarith release archive and every archived file."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key


def canonical_json(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def public_key_sha256(public_key_path: Path) -> str:
    return sha256_bytes(public_key_path.read_bytes())


def safe_member_name(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and "\\" not in name


def verify_bundle(
    archive_path: Path,
    manifest_path: Path,
    signature_path: Path,
    public_key_path: Path,
) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("bundle manifest must be a JSON object")
    public_key = load_pem_public_key(public_key_path.read_bytes())
    if not isinstance(public_key, Ed25519PublicKey):
        raise ValueError("bundle public key must be Ed25519")
    signature = base64.b64decode(signature_path.read_text(encoding="ascii").strip(), validate=True)
    try:
        public_key.verify(signature, canonical_json(manifest))
    except InvalidSignature as error:
        raise ValueError("bundle manifest signature is invalid") from error

    archive = manifest.get("archive")
    files = manifest.get("files")
    if not isinstance(archive, dict) or not isinstance(files, list):
        raise ValueError("bundle manifest structure is invalid")
    archive_bytes = archive_path.read_bytes()
    if archive.get("filename") != archive_path.name:
        raise ValueError("archive filename does not match manifest")
    if archive.get("size") != len(archive_bytes):
        raise ValueError("archive size does not match manifest")
    if archive.get("sha256") != sha256_bytes(archive_bytes):
        raise ValueError("archive hash does not match manifest")

    expected: dict[str, dict[str, object]] = {}
    for entry in files:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError("bundle file entry is invalid")
        name = entry["path"]
        if not safe_member_name(name) or name in expected:
            raise ValueError(f"unsafe or duplicate bundle path: {name}")
        expected[name] = entry

    with zipfile.ZipFile(archive_path) as bundle:
        names = bundle.namelist()
        if any(not safe_member_name(name) for name in names) or len(names) != len(set(names)):
            raise ValueError("archive contains an unsafe or duplicate path")
        if set(names) != set(expected):
            raise ValueError("archive file list does not match manifest")
        for name, entry in expected.items():
            content = bundle.read(name)
            if entry.get("size") != len(content):
                raise ValueError(f"file size mismatch: {name}")
            if entry.get("sha256") != sha256_bytes(content):
                raise ValueError(f"file hash mismatch: {name}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--signature", type=Path)
    parser.add_argument("--public-key", type=Path)
    parser.add_argument(
        "--expected-public-key-sha256",
        help="SHA-256 fingerprint obtained through a separate trusted channel",
    )
    args = parser.parse_args()
    base = args.archive.with_suffix("")
    manifest = args.manifest or Path(f"{base}.manifest.json")
    signature = args.signature or Path(f"{base}.manifest.sig")
    public_key = args.public_key or Path(f"{base}.public.pem")
    actual_fingerprint = public_key_sha256(public_key)
    if (
        args.expected_public_key_sha256
        and actual_fingerprint.lower() != args.expected_public_key_sha256.lower()
    ):
        parser.error("public key SHA-256 does not match the trusted fingerprint")
    payload = verify_bundle(args.archive, manifest, signature, public_key)
    print(
        f"Verified {args.archive.name}: {payload.get('release_id')} "
        f"({payload.get('channel')})"
    )
    print(f"Public key SHA-256: {actual_fingerprint}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
