# Authoring & Maintaining GameData v4 Packs

This guide covers authoring new game packs (with an AI coding agent or by hand), validating them locally, packing icons, and publishing release archives from `factory-planner-packs`.

---

## 1. Prerequisites

1. **`gamedata_tool`**: Download a Factory Planner release matching `tool.version` (or build `gamedata_tool` from the `factory-planner` C++ repo) and place `gamedata_tool` on your `PATH`.
   Verify with:
   ```bash
   gamedata_tool --version
   ```
2. **Python 3 (standard library first)**: Converters default to the Python 3 standard library (`json`, `csv`, `xml.etree`, `zipfile`, `gzip`, `sqlite3`, `struct`, `zlib`) plus shared stdlib helpers under `common/` (such as `common/png_resize.py` and `common/slug.py`). Already-installed system tools (e.g. ImageMagick) are also fine.
   - Third-party Python packages are allowed **only** inside a project-local `.venv/` with a pinned `requirements.txt` (recorded in `PACK_NOTES.md`).
   - **Never** run global or `--user` `pip install`, `--break-system-packages`, or `sudo` installs.
3. **CMake** (optional, maintainer release step): used for cross-platform zip creation via `cmake -E tar cf ... --format=zip`.

---

## 2. Quick Start — AI-Assisted Pack Authoring

1. Place your raw game dump (and optional source icons and `NOTES.md`) in `raw/<game>/` (gitignored).
2. Gather authoritative references for the **exact game/modpack version** you are targeting:
   - official wiki URLs,
   - game or mod source repositories (branch/tag/commit), or
   - a local `raw/<game>/NOTES.md` documenting verified mechanics and formulas.
3. Start an AI coding agent in the root of this repository and paste:

```text
You are helping me build a Factory Planner game-data pack in this folder. My raw game data
is in raw/. Run `gamedata_tool guide prompt` and follow it exactly. Then run
`gamedata_tool guide reference` and read it fully before proposing anything.
```

The embedded prompt walks through seven structured phases with human stop-gates:

| Phase | What happens | Human stop-gate? |
|---|---|---|
| **0 Setup / Resume** | Verifies `gamedata_tool --version`, reads `guide reference`, resumes from `PACK_NOTES.md` if present. | Resume confirmation only |
| **1 Discovery** | Samples `raw/<game>/`, proposes a raw → v4 mapping table, asks you for exact version, authoritative references, and scope. | **Yes** |
| **2 Mechanics & Template** | Proposes Decision Cards (max 5/turn) grounded in your references (never memory), writes `template/game.json` with source+version citations, smoke-tests it. | **Yes** |
| **3 Hand-Checked Cases** | Computes 3–10 representative recipes by hand showing arithmetic and citations; writes `cases/*.json`. | **Yes** |
| **4 Converter Loop** | Writes `converters/<game>/convert/`, loops `convert` → `validate --no-icons --werror --json` until 0 errors and 0 warnings, checks byte-identical determinism. | Autonomous |
| **5 Verify & Icons** | Runs `eval --cases`, reconciles `stats` with `report.json`, runs `--sweep` checks, and optionally resizes/checks/packs icons. | Autonomous |
| **6 Handover** | Updates `PACK_NOTES.md` with decisions, formulas & sources, limitations, and exact rerun commands. | Review & test in app |

---

## 3. Manual Authoring & Converter Rules

Whether written by a human or an agent, every converter in `converters/<game>/` must follow these rules:

1. **Read-only `raw/`, generated `packs/`:** Never hand-edit generated files in `packs/<game>/<pkg>/`. Put manual tweaks in `converters/<game>/template/overrides.json` or `template/game.json` and rerun.
2. **Scoped writes:** Delete and rewrite **only** the JSON files inside the targeted `packs/<game>/<pkg>/` (plus `converters/<game>/report.json` and `.tmp_icons/`). Never touch sibling package versions or `icons.pak`.
3. **Deterministic output:** Same raw input → byte-identical JSON (stable key/entity sorting, fixed float formatting, strict JSON with `allow_nan=False`, no timestamps).
4. **Stable identity & port order:**
   - Derive entity IDs from stable internal/class keys, never display names, and slugify to `[a-z0-9_-]+` matching `slugify()` (see `gamedata_tool guide reference` §8.2).
   - For recipes without a raw ID (e.g. GTNH), hash canonical inputs/outputs under `<category>-<short_hash>`.
   - **Never reorder recipe `in`/`out` ports arbitrarily** — port slot indices (`in:0`, `out:0`, …) are identity in `.fpp` project files.
5. **Formulas in templates only:** All expressions live in `template/game.json` profiles. Recipes are pure data using compact short tuple ports `[res, amount]` / `[res, amount, chance]` and sharded under `recipes/*.json` for large packs.
6. **No silent drops:** Record every skipped record, merged duplicate port (`V-W-3`), and ID collision in `report.json`, and reconcile counts against `gamedata_tool stats`.
7. **Warning-free (`--werror`):** Prune unused resources/machines/parameters/tables/metrics (`V-W-2`) and merge identical duplicate ports (`V-W-3`).
8. **Source-cited formulas:** Document every non-trivial formula, constant, and lookup table with its exact source URL / repo path and game/mod version in `PACK_NOTES.md` and `template/game.json` `"notes"`.

---

## 4. Local Validation & Icon Workflow

Run these checks before opening a PR (CI runs the first two automatically):

```bash
# 1. Strict JSON & schema validation (no icons, matches CI)
gamedata_tool validate packs/<game>/<pkg> --no-icons --werror

# 2. Regression cases (all must PASS)
gamedata_tool eval packs/<game>/<pkg> --cases converters/<game>/cases

# 3. Entity counts & load-time budget (< 2 s for 50k recipes in Release)
gamedata_tool stats packs/<game>/<pkg> --timing --repeat 5
```

### Optional icon pipeline (local only — never commit icons)

Icons must be **square PNGs ≤ 64×64** (`V-ICON-1`), laid out under `<dir>/{resources/<id>.png, machines/<id>.png, options/<set>/<key>.png}`:

```bash
# 1. Resize/pad source icons into .tmp_icons/<game>/<pkg>/ (via your converter or common/png_resize.py)
# 2. Check missing, unreferenced, case mismatches, and V-ICON-1
gamedata_tool check-icons packs/<game>/<pkg> --from .tmp_icons/<game>/<pkg> --werror

# Optional: remove unreferenced loose PNGs before packing
gamedata_tool prune-icons packs/<game>/<pkg> --from .tmp_icons/<game>/<pkg>
gamedata_tool prune-icons packs/<game>/<pkg> --from .tmp_icons/<game>/<pkg> --apply

# 3. Build and byte-verify <package_root>/icons.pak
gamedata_tool pack-icons packs/<game>/<pkg> --from .tmp_icons/<game>/<pkg> --verify

# 4. Full validation including icons.pak
gamedata_tool validate packs/<game>/<pkg> --werror
```

A pack without icons is completely valid ("no icons" mode): omit `icons/` and `icons.pak`, and `validate --werror` passes with one info note.

---

## 5. Maintainer Release Workflow

Because raw dumps and icons stay out of git, release archives are built locally from a clean checkout with local `raw/` dumps present:

1. For every `<game>/<pkg>` to publish:
   ```bash
   # Regenerate JSON + resized icons (see converters/<game>/PACK_NOTES.md)
   gamedata_tool check-icons packs/<game>/<pkg> --from .tmp_icons/<game>/<pkg> --werror
   gamedata_tool pack-icons  packs/<game>/<pkg> --from .tmp_icons/<game>/<pkg> --verify
   gamedata_tool validate    packs/<game>/<pkg> --werror
   gamedata_tool eval        packs/<game>/<pkg> --cases converters/<game>/cases
   ```
2. Package **only JSON files and `icons.pak`** (no loose `icons/` directory!) into `<game>-<pkg>.zip` rooted at `<game>/<pkg>/`:
   ```bash
   mkdir -p dist
   # Stage JSON + icons.pak cleanly without loose icons/
   # Then archive using CMake (works identically on Linux, macOS, and Windows):
   cmake -E tar cf dist/<game>-<pkg>.zip --format=zip -- <game>/<pkg>
   ```
   *(Run `cmake -E tar` from a staging directory containing `<game>/<pkg>/{game.json, *.json, recipes/..., icons.pak}` so the archive extracts cleanly into `game_data/<game>/<pkg>/`.)*
3. Create a GitHub Release tagged `packs-YYYY.MM.DD` and upload all `dist/<game>-<pkg>.zip` files.
4. Update `packs.ref` in the main `factory-planner` repository to `packs-YYYY.MM.DD` so the next app release downloads and validates those archives automatically.

---

## 6. Pull Request Checklist

- [ ] No files from `raw/`, `icons/`, `icons.pak`, `report.json`, `.tmp_icons/`, or `.venv/` are staged or committed.
- [ ] `gamedata_tool validate packs/<game>/<pkg> --no-icons --werror` exits `0`.
- [ ] `gamedata_tool eval packs/<game>/<pkg> --cases converters/<game>/cases` passes 100%.
- [ ] Running the converter twice produces `git diff` empty (byte-identical determinism).
- [ ] `converters/<game>/PACK_NOTES.md` records the exact game version, authoritative references, decision log, formulas & sources table, and rerun commands.
- [ ] GitHub Actions `validate.yml` is green on the PR.
