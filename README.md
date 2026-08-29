# 🎬 bazarr-providers

Subtitle providers for **[Bazarr+](https://github.com/LavX/bazarr)**, focused on
sources the mainstream providers cover poorly.

> [!NOTE]
> These are **Provider Hub plugins** and require Bazarr+. Upstream Bazarr has no
> plugin system, so it is not supported here.

| Provider | Language | Source | Notes |
|---|---|---|---|
| **[SubKade](providers/subkade)** | Persian (fas) | [subkade.ir](https://subkade.ir) | Per-season archives, matched by IMDB id |

More may follow — the layout and tooling are built for several.

---

## 📦 Install on Bazarr+ (Provider Hub)

Bazarr+ runs providers as sandboxed plugins: each in its own virtualenv,
out-of-process, hash-verified against its manifest, and unaffected by Bazarr
updates. Three ways in, easiest first.

### 1️⃣ Add this repo as a catalog source ⭐ recommended

Install and update from the Marketplace like any other provider — no files to
download, and updates appear automatically.

**Subtitle Hub → Marketplace → Manage sources**, then:

**GitHub catalog URL**

```
https://github.com/mamal72/bazarr-providers/blob/main/catalog.json
```

**Name**

```
mamal72/bazarr-providers
```

**Add source**, then install **SubKade** from the Marketplace list.

> [!NOTE]
> Community sources show as untrusted — that badge only means the source is not
> on Bazarr+'s own trusted list. It says nothing about the plugin. Review the
> [manifest](providers/subkade/provider.json) before installing, as you should
> with any third-party catalog.

### 2️⃣ Download a prebuilt package

Grab `subkade-hub.zip` from the
[latest release](https://github.com/mamal72/bazarr-providers/releases/latest),
then **Subtitle Hub → Marketplace → Install local package**.

### 3️⃣ Build the package yourself

Nothing to install — the builder is stdlib Python:

```bash
git clone https://github.com/mamal72/bazarr-providers.git
cd bazarr-providers
python3 scripts/build_zip.py subkade      # -> subkade-hub.zip
```

Builds are deterministic: the same source always produces a byte-identical
archive. Then install it as in ②.

### ⚠️ After installing, enable it

Installing does not enable. In **Subtitle Hub → My Providers**, click
**+ Add search provider**, choose the provider, and **save settings**.

---

## 🧩 Providers

### SubKade — Persian

SubKade publishes **one archive per season** rather than per-episode files, so
the provider:

1. Resolves the series by its **IMDB id** (`https://subkade.ir/?s=tt1234567`),
   which returns exactly one page — no fuzzy title matching, so no wrong-show
   results.
2. Reads the per-season archive links from that page.
3. Downloads the season archive **once**, caches it for the life of the worker,
   and lists entries matching the requested episode.
4. Serves the chosen entry on download.

Fetching several episodes of one season therefore costs a single download.

**No configuration.** Archives use the same episode numbers Bazarr does — a
two-part episode is filed under its first number (`S04E01E02` lives in the
`E01` folder and answers for both halves), so nothing needs translating.
Entries naming their release are offered ahead of bare filenames, since Bazarr
can score those against the video.

#### 📝 Notes

- `subkade.ir` is reachable directly from Iran and does **not** need proxying.
  If Bazarr routes through a VPN, add `subkade.ir` and `dl1.subkade.ir` to the
  proxy exclusions — some hosts return 403 to datacenter IPs.
- Archives are `.zip`. SubKade occasionally publishes `.rar`, which the standard
  library cannot read; those entries are skipped.
- Subtitles are served as-is. Persian files sometimes need a leading RLM
  (U+200F) for dialogue dashes to render correctly in some players — a property
  of the source files, not this provider.

---

## 🛠️ Development

```
providers/<id>/provider.py     Hub plugin — stdlib only, no Bazarr imports
providers/<id>/provider.json   manifest (hashes must match the source)
tests/                         unit tests + fixtures captured from the live site
catalog.json                   generated; what Bazarr+ fetches as a catalog
```

```bash
python3 -m unittest discover -s tests   # tests
python3 scripts/check_hashes.py         # manifest hashes match the source
python3 scripts/build_catalog.py        # regenerate catalog.json
python3 scripts/build_zip.py --all      # build every package
```

`providers/<id>/` must contain **only** `*.py` and `provider.json` — the Hub's
verifier rejects anything else, and the manifest's file map is built by globbing
`*.py` recursively. Anything else belongs outside `providers/`.

Regenerate `provider.json` hashes with the upstream
[catalog SDK](https://github.com/LavX/bazarr-provider-catalog)
(`python3 -m sdk hash providers/<id>`); `scripts/check_hashes.py` reproduces its
digest and fails CI when a manifest is stale.

## ✅ Requirements

- **Bazarr+** — these are Provider Hub plugins; upstream Bazarr cannot load them

No provider here needs an account, API key, or configuration.

## 📄 License

MIT
