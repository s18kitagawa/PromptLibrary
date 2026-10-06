---
name: stock-screening
description: Screen one year of a dated photo archive (YYYY/YYYY-MM-DD) for Adobe Stock candidates - automatic technical filter, numbered contact sheets, visual review, recorded decisions. Use when asked to screen or pick stock photos for a year, e.g. "screen 2020 for Adobe Stock" or "2020をやって".
---

# Stock screening (Claude Cowork)

Run steps 1-2 of the stock-screening pipeline for **one year** and leave a reviewed
`review.csv` in the output folder. Photos are read-only: never move, rename, edit or
delete anything in the photo archive.

The user names a year (`YYYY`). If they did not, ask which year.

## 0. Locate folders and prepare the environment

Three folders must be connected to the session (ask the user to connect any that are missing):

| Role | How to recognise it |
|---|---|
| Code (this repo) | contains `pyproject.toml` with `name = "stock-screening"` |
| Photo archive | contains `YYYY/` folders with `YYYY-MM-DD/` subfolders |
| Output folder | anything else the user designated for results; must be outside the other two |

In `device_bash`, connected folders are mounted under `$HOME/mnt/<folder-name>`.
Note each folder's **device path** too (from `get_device_info` / `device_list_dir`) -
`device_stage_files` needs it.

Set up once per session (keeps the Linux virtualenv out of the user's folders):

```bash
export UV_PROJECT_ENVIRONMENT=$HOME/.venvs/stock-screening PYTHONDONTWRITEBYTECODE=1
cd $HOME/mnt/<code-folder> && uv sync --frozen
```

Every later call: same `export` and `cd`, then
`uv run --frozen stock-screening --photos-root $HOME/mnt/<archive> --out-dir $HOME/mnt/<output> <command> --year YYYY`
(below abbreviated as `ss <command>`).

## 1. Automatic screening

1. `ss status` - see where this year stands; resume from the first unfinished step.
2. `ss scan --time-budget 150` - repeat until it prints `SCAN COMPLETE`
   (exit code 3 = time budget hit, just run it again; results are cached).
3. `ss select` - prints pass/reject counts by reason. Report them to the user.
   If the pass rate looks wrong (e.g. almost everything rejected as `soft_focus`),
   suggest a threshold change in `config.local.toml` and re-run `select` (no rescan needed).
4. `ss sheets` - renders `sheets/sheet_NNN.jpg` (20 numbered tiles each) and `sheets/index.csv`.
   Files that already have a decision are skipped, so re-running resumes the review.

## 2. Visual review

Work through the sheets in order. For each batch of up to ~10 sheets:

1. `device_stage_files` with the device paths of `<output>/<YYYY>/sheets/sheet_NNN.jpg`.
2. `Read` each staged sheet and judge every tile.
3. Record decisions **before** moving on (so progress survives interruptions), grouping IDs:
   `ss mark --ids 1-3,7 --decision candidate`
   `ss mark --ids 5 --decision review --flags people --note "faces visible"`
   `ss mark --ids 4,6,8-20 --decision reject`
   Every tile on a reviewed sheet must get a decision.

### Criteria (Adobe Stock)

- **candidate** - technically sound at preview size, a subject a buyer could use
  (travel, city, nature, food, objects, textures, seasonal events, night illuminations,
  backgrounds/copy space), clean composition, and none of the review/reject issues below.
- **review** - promising but needs the user's judgement. Set flags:
  `people` (recognisable person -> model release), `logo` / `text` (brands, signage,
  legible text), `landmark` / `artwork` (buildings, sculptures, murals that may need a
  property release or be restricted), `private` (private home, documents, screens),
  `focus` / `noise` (unsure at preview size), `similar` (near-duplicate of another candidate:
  note the other ID), `composition`.
- **reject** - personal snapshots without commercial use, failed exposures, strong motion
  blur, cluttered/accidental frames, weaker duplicates of a better frame, screenshots,
  or content that cannot be cleared (crowds of identifiable faces, prominent trademarks).

Be selective: Adobe Stock rejects mediocre or redundant images. When unsure between
candidate and reject, use `review` with a flag rather than guessing.

## 3. Wrap up

1. `ss status` - confirm `not yet reviewed 0`.
2. `ss export --decision candidate --path-prefix "<device path of the photo archive>"`
   writes `export_candidate.txt` with macOS paths (input for the Lightroom step).
3. Report to the user: counts per decision, notable themes among the candidates, the
   `review` items grouped by flag, and the output file locations.

## Privacy rules

- Outputs (CSV, JSONL, sheets) stay in the output folder. Never copy them into the code
  repository, a project, an artifact or any upload.
- Describe photos to the user only as far as needed for the review summary.
