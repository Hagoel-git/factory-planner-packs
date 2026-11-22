# Factory Planner Packs

Official and community **GameData v4** game packs, deterministic converter pipelines, and regression suites for [Factory Planner](https://github.com/Hagoel-git/factory-planner).

> **Text-only repository:** Raw game dumps, extracted icons, and `icons.pak` containers are **never committed to git**. Complete ready-to-use pack archives (`<game>-<pkg>.zip`, containing GameData v4 JSON plus `icons.pak`) are published on the [Releases](../../releases) page and bundled into Factory Planner releases via `packs.ref`.

---

## Repository Layout

```text
factory-planner-packs/
  README.md                         this file
  AUTHORING.md                      pack authoring, AI workflow, and release packaging guide
  NOTICE                            third-party game assets & trademark notice
  tool.version                      Factory Planner release tag providing gamedata_tool for CI
  common/                           shared Python 3 stdlib helpers (e.g. png_resize.py, slug.py)
  converters/<game>/
    template/game.json              manifest, units, kinds, attributes, params, metrics, profiles
    template/overrides.json         data-only hand fixes (renames, exclusions, extra attrs/ports)
    convert/                        deterministic converter scripts (data + optional icon step)
    cases/*.json                    hand-verified `gamedata_tool eval --cases` regression tests
    PACK_NOTES.md                   provenance, authoritative sources, decisions, rerun commands
  packs/<game>/<pkg>/               generated GameData v4 JSON (committed; validated by CI)
  .github/workflows/validate.yml    CI: validates all packs (--no-icons --werror) + runs eval cases
```

Gitignored working directories used locally while authoring:
- `raw/<game>/` — your local game data dumps and source icons (read-only for converters/agents)
- `.tmp_icons/` — icon resize scratch directory
- `packs/<game>/<pkg>/icons/` and `packs/<game>/<pkg>/icons.pak` — generated local icons
- `converters/<game>/report.json` — generated converter summary / skipped-record report
- `.venv/` — optional project-local virtual environment (only when explicitly needed)

---

## Using Packs

### End users
Factory Planner official releases already bundle the release packs pinned in `packs.ref`. To install or update an individual pack manually:

1. Download `<game>-<pkg>.zip` from the latest **Releases** page.
2. Extract it into your Factory Planner `game_data/` folder so the manifest sits at `game_data/<game>/<pkg>/game.json` (with `icons.pak` next to it).
3. Restart Factory Planner (or rescan game data).

### Local development (without `icons.pak`)
You can point Factory Planner directly at a checkout of this repository using `--game_data_dir`:

```bash
factory_planner --game_data_dir /path/to/factory-planner-packs/packs
```

Packs checked out from git have no icons by default; Factory Planner runs them in valid **"no icons" mode** (placeholder icons, or icons borrowed from other installed packs if **Appearance → Icons → Cross-pack icon fallback** is enabled in Settings).

---

## Contributing or Adding a Game Pack

See [AUTHORING.md](AUTHORING.md) for the full guide, including:
- the AI-assisted converter workflow (`gamedata_tool guide prompt` + `gamedata_tool guide reference`),
- converter determinism and dependency rules,
- validation, regression cases, and icon packing (`check-icons`, `pack-icons`),
- the maintainer release packaging checklist.

---

## License & Assets Notice

Converter scripts, templates, and GameData v4 JSON metadata in this repository are distributed under the repository license. Game names, item/machine names, formulas, and any optional icon assets distributed in Release zips remain the property of their respective copyright holders; see [NOTICE](NOTICE).
