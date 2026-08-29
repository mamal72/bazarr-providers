#!/usr/bin/env python3
"""Fail if provider.json's hashes do not match the source on disk.

A stale `bundle_sha256` or file digest is only discovered at install time,
where it surfaces as a bundle-verification failure with no hint that the
manifest simply was not regenerated after an edit.

Mirrors the SDK's own hashing so the repo can be checked without vendoring it.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS_DIR = ROOT / "providers"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bundle_sha256(manifest: dict, provider_dir: Path) -> str:
    """Digest over the manifest's declared files, in sorted order.

    Must match sdk.cli.bundle_sha256 exactly: path, NUL, byte-length, NUL,
    raw contents, NUL - the raw bytes, not their hex digest. Getting this
    subtly wrong yields a plausible-looking hash that fails only at install.
    """
    digest = hashlib.sha256()
    for relative in sorted(manifest.get("files", {})):
        data = (provider_dir / relative).read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(data)).encode("ascii"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return digest.hexdigest()


def check(provider_dir: Path) -> list[str]:
    manifest = json.loads((provider_dir / "provider.json").read_text())
    PROVIDER_DIR = provider_dir
    problems = []
    for relative, declared in sorted(manifest.get("files", {}).items()):
        path = PROVIDER_DIR / relative
        if not path.is_file():
            problems.append("declared file is missing: %s" % relative)
            continue
        actual = file_sha256(path)
        if actual != declared:
            problems.append(
                "files[%s] is stale\n  declared %s\n  actual   %s"
                % (relative, declared, actual)
            )

    for path in sorted(PROVIDER_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(PROVIDER_DIR).as_posix()
        if relative not in manifest.get("files", {}):
            problems.append("file is not declared in the manifest: %s" % relative)

    declared_bundle = manifest.get("bundle_sha256")
    actual_bundle = bundle_sha256(manifest, PROVIDER_DIR)
    if declared_bundle != actual_bundle:
        problems.append(
            "bundle_sha256 is stale\n  declared %s\n  actual   %s"
            % (declared_bundle, actual_bundle)
        )

    return problems


def main() -> int:
    failed = False
    for provider_dir in sorted(PROVIDERS_DIR.iterdir()):
        if not (provider_dir / "provider.json").is_file():
            continue
        problems = check(provider_dir)
        if problems:
            failed = True
            print("%s: manifest is out of date" % provider_dir.name, file=sys.stderr)
            for problem in problems:
                print("  %s" % problem, file=sys.stderr)
        else:
            manifest = json.loads((provider_dir / "provider.json").read_text())
            print("%s: hashes match (bundle %s)"
                  % (provider_dir.name, manifest["bundle_sha256"][:16] + "..."))
    if failed:
        print("\nregenerate the affected manifest, e.g. with the catalog SDK:"
              "\n  python3 -B -m sdk hash providers/<id>", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
