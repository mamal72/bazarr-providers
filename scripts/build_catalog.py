#!/usr/bin/env python3
"""Generate catalog.json from every providers/*/provider.json.

This is the file Bazarr+ fetches when the repo is added under
Subtitle Hub -> Marketplace -> Manage sources. Its shape mirrors the official
catalog: a name, a schema version, and each provider's manifest wrapped in
{"manifest": ...}.

`source.commit` stays a zero placeholder. Bazarr+ resolves `source.ref` to a
real commit through the GitHub API when it installs, so pinning one here would
mean rewriting every manifest on every commit.

  python3 scripts/build_catalog.py            # write catalog.json
  python3 scripts/build_catalog.py --check    # fail if it is out of date
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS_DIR = ROOT / "providers"
CATALOG = ROOT / "catalog.json"
CATALOG_NAME = "mamal72/bazarr-providers"
SCHEMA_VERSION = 1


def build() -> dict:
    providers = []
    for provider_dir in sorted(PROVIDERS_DIR.iterdir()):
        manifest_path = provider_dir / "provider.json"
        if not manifest_path.is_file():
            continue
        providers.append({"manifest": json.loads(manifest_path.read_text())})
    return {
        "name": CATALOG_NAME,
        "providers": providers,
        "schema_version": SCHEMA_VERSION,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    catalog = build()
    rendered = json.dumps(catalog, indent=2, sort_keys=True) + "\n"

    if args.check:
        current = CATALOG.read_text() if CATALOG.is_file() else ""
        if current != rendered:
            print("catalog.json is out of date - run: python3 scripts/build_catalog.py",
                  file=sys.stderr)
            return 1
        print("catalog.json is up to date (%d providers)" % len(catalog["providers"]))
        return 0

    CATALOG.write_text(rendered)
    print("wrote catalog.json (%d providers)" % len(catalog["providers"]))
    for entry in catalog["providers"]:
        m = entry["manifest"]
        print("  %-12s v%-8s %s" % (m["provider_id"], m["version"], m["name"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
