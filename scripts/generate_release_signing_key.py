"""Generate the offline Ed25519 key pair used for release manifests."""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
import subprocess
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRIVATE_KEY = ROOT / ".runtime" / "release_private_key.pem"
DEFAULT_PUBLIC_KEY = ROOT / "backend" / "app" / "release_public_key.pem"


def write_private_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
    if os.name == "nt":
        identity = subprocess.run(
            ["whoami.exe", "/user", "/fo", "csv", "/nh"],
            check=True,
            capture_output=True,
            text=True,
        )
        sid = next(csv.reader([identity.stdout.strip()]))[1]
        subprocess.run(
            ["icacls.exe", str(path), "/inheritance:r", "/grant:r", f"*{sid}:(F)"],
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-key", type=Path, default=DEFAULT_PRIVATE_KEY)
    parser.add_argument("--public-key", type=Path, default=DEFAULT_PUBLIC_KEY)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.force and (args.private_key.exists() or args.public_key.exists()):
        parser.error("key file already exists; use --force only for intentional key rotation")
    if args.force:
        args.private_key.unlink(missing_ok=True)

    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    write_private_file(args.private_key, private_pem)
    args.public_key.parent.mkdir(parents=True, exist_ok=True)
    args.public_key.write_bytes(public_pem)
    print(f"private key: {args.private_key}")
    print(f"public key: {args.public_key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
