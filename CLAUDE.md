# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Kill Team 2024 probability calculator — a tablet-friendly single-page web app. Drop GW PDF datacards into `source/`, run `build.py` to parse them into a self-contained `killteam.html`, then open that file directly in any browser (no web server needed).

## Commands

```bash
# One-time setup — creates .venv and installs dependencies
uv sync

# Parse all PDFs in source/ and regenerate killteam.html
uv run python build.py

# Parse a single PDF
uv run python build.py --pdf source/MyTeam.pdf

# Dump parsed JSON to stdout (useful for debugging)
uv run python build.py --dump
```

## Architecture

### File roles

| File | Role |
|------|------|
| `template.html` | Source file — edit this, not `killteam.html` |
| `killteam.html` | Generated output; overwritten every build |
| `build.py` | PDF parser → injects team data into template → writes killteam.html |
| `source/*.pdf` | GW official datacards; add PDFs here, then rebuild |

### Data flow

`source/*.pdf` → `build.py` (pdfplumber) → `TEAMS_DATA` JS object → injected into `template.html` at `/*TEAMS_DATA_PLACEHOLDER*/` → `killteam.html`

The `TEAMS_DATA` object is embedded directly in a `<script>` block so the file opens as `file://` with no server.

### PDF format (KT 2024)

GW 2024 datacards use this block structure per operative (each block is one pdfplumber table cell):

```
APL MOVE SAVE WOUNDS
OPERATIVE NAME
3 6" 3+ 15
NAME ATK HIT DMG WR
Bolt rifle 4 3+ 3/4 Piercing Crits 1
Chainsword 5 3+ 4/5 -
```

- `DMG` is `normal_damage/crit_damage` (e.g. `3/5`)
- `WR` is free-text weapon rules (Ceaseless, Piercing X, Lethal 5+, etc.)
- DF is always 3 in KT 2024 (hardcoded; not printed on cards)
- OCR artifacts like `"T orrent"` are cleaned up by a regex pre-pass

### Rule mapping

KT 2024 rule names are mapped to internal calculator IDs in `build.py::RULE_MAP`. Key mappings:
- `Piercing X` / `Piercing Crits X` → `apX` (reduces defense dice)
- `Lethal 5+` → `lethal5` (lowers crit threshold to 5)
- `Devastating X` → `mwX` (mortal wounds on each unblocked crit)
- `Torrent` → treat BS as 2 (near auto-hit)

Rules with no damage impact (Heavy, Silent, Saturate, etc.) are stored and shown as informational tags in the UI.

### Probability engine (`template.html` — `computeAttack()`)

Uses exact dynamic programming, not Monte Carlo. Returns a full `P(damage=k)` distribution.

Attack sequence:
1. Compute per-die probabilities (adjusted for Ceaseless/Relentless/Lethal)
2. DP over `A` dice → joint distribution of `(crit_hits, normal_hits)`
3. Apply Rending post-roll if active
4. DP over `max(0, DF − AP + cover)` defense dice → `(crit_saves, normal_saves)`
5. Resolve: crit_saves cancel crit_hits first; excess crit_saves become normal saves; remaining saves cancel hits; unblocked dice deal damage
6. Severe post-roll: if 0 crits retained, convert 1 normal hit to a crit; Devastating X fires immediately on each retained crit (even if that crit is later blocked)
7. Sum over all attack/defense combinations weighted by their joint probability

### UI state model

`state` object in `template.html` tracks: selected team/operative/weapon for attacker and defender, active manual rule overrides (`Set`), active ploy/equipment IDs (`Set`), cover toggle, injured toggle. Every change calls `recalculate()` which redraws results and the Chart.js bar chart.

### Adding a new team manually

Edit `template.html` and find the `TEAMS_DATA` placeholder comment, then add a new entry following the existing schema. Or add a PDF to `source/` and rebuild.

### Known parser limitations

- Weapon rules that wrap across PDF lines are handled by a continuation heuristic (appends extra rules to the previous weapon if the line contains no stat numbers)
- Equipment and ploy effects are not auto-parsed from PDFs — add them manually to the team dict in `template.html` or a custom build step
- Some non-standard weapon names may misclassify ranged/melee; fix by adding keywords to `MELEE_KEYWORDS` in `build.py`
