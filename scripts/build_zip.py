#!/usr/bin/env python3
"""Build a Bazarr+ Provider Hub package for one provider in this repo.

The Hub's bundle verifier rejects any file that is not `*.py` or
`provider.json`, so a package contains only those - no README, no tests, no
dotfiles. Anything else fails at install time with an error that does not
explain itself.

  python3 scripts/build_zip.py subkade
  python3 scripts/build_zip.py --all
  python3 scripts/build_zip.py subkade --check   # list contents, write nothing
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS_DIR = ROOT / "providers"
ALLOWED_NAMES = {"provider.json"}


def provider_ids():
    return sorted(
        path.name for path in PROVIDERS_DIR.iterdir()
        if path.is_dir() and (path / "provider.json").is_file()
    )


def collect(provider_dir: Path):
    """Files the Hub will accept, as (path, arcname) pairs."""
    members = []
    for path in sorted(provider_dir.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(provider_dir).as_posix()
        if path.suffix != ".py" and relative not in ALLOWED_NAMES:
            continue
        members.append((path, relative))
    return members


def build(provider_id: str, out: Path | None, check: bool) -> int:
    provider_dir = PROVIDERS_DIR / provider_id
    if not (provider_dir / "provider.json").is_file():
        print("error: no such provider: %s" % provider_id, file=sys.stderr)
        return 1

    members = collect(provider_dir)
    names = [name for _, name in members]
    for required in ("provider.json", "provider.py"):
        if required not in names:
            print("error: %s missing from %s" % (required, provider_dir), file=sys.stderr)
            return 1

    if check:
        print("%s: %d files" % (provider_id, len(names)))
        for name in names:
            print("  %s" % name)
        return 0

    out = out or ROOT / ("%s-hub.zip" % provider_id)
    # Deterministic: fixed timestamps and sorted members, so the same source
    # always produces a byte-identical archive.
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, name in members:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    print("wrote %s (%d files, %d bytes)" % (out, len(members), out.stat().st_size))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("provider", nargs="?", help="provider id, e.g. subkade")
    parser.add_argument("--all", action="store_true", help="build every provider")
    parser.add_argument("--out", help="output path (single provider only)")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.all:
        return max(build(pid, None, args.check) for pid in provider_ids())
    if not args.provider:
        print("provider ids: %s" % ", ".join(provider_ids()), file=sys.stderr)
        return 2
    return build(args.provider, Path(args.out) if args.out else None, args.check)


if __name__ == "__main__":
    raise SystemExit(main())
