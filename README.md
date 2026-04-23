# Kill Team Calculator

A probability calculator for **Kill Team 2024**. Drop GW PDF datacards into `source/`, run one command, and open `killteam.html` in any browser — no server required.

## Features

- **Exact probability distributions** — dynamic programming, not Monte Carlo
- **Ranged attacks** — full save resolution with cover, AP, Obscured, accurate hits, re-rolls
- **Fight (melee)** — both sides pick melee weapons, alternate strike/block, three strategies (All Attack / Minimize Damage / Optimal), Multiblock support
- **Mid-fight death tracking** — if a fighter is killed during resolution, their remaining dice are forfeited
- **Weapon rules** — Ceaseless, Relentless, Balanced, Rending, Severe, Lethal 5+/4+, Devastating X, Brutal, Torrent
- **Charts** — exact damage bar chart, "at least X" survival curve
- **Light / dark mode** toggle
- **Tablet-friendly** single-page app

## Quickstart

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)

### Setup

```bash
# Install dependencies into an isolated virtual environment
uv sync
```

### Add datacards

Copy GW official PDF rules from Warhammer Community into `source/`:

```
source/

```

### Build

```bash
uv run python build.py
```

This parses every PDF in `source/` and writes a self-contained `killteam.html`.

```bash
# Build a single PDF
uv run python build.py --pdf source/MyTeam.pdf

# Print extracted JSON without writing killteam.html (useful for debugging)
uv run python build.py --dump
```

### Open

Double-click `killteam.html` or open it with `file://` in any browser. No web server needed.

## How it works

### PDF parsing

`build.py` uses [pdfplumber](https://github.com/jsvine/pdfplumber) to extract operative stats and weapon profiles from GW 2024 datacards. The parsed data is serialized as a JavaScript object and injected into `template.html` at the `/*TEAMS_DATA_PLACEHOLDER*/` marker, producing `killteam.html`.

GW 2024 datacard block format (one block per operative):

```
APL  MOVE  SAVE  WOUNDS
OPERATIVE NAME
3    6"    3+    15
NAME          ATK  HIT  DMG   WR
Bolt rifle    4    3+   3/4   Piercing Crits 1
Chainsword    5    3+   4/5   -
```

- `DMG` is `normal/crit` (e.g. `3/4`)
- `DF` is always 3 in KT 2024 and is hardcoded
- OCR artifacts (e.g. `"T orrent"`) are cleaned by a regex pre-pass

### Probability engine

The ranged attack engine (`computeAttack`) and fight engine (`computeFight`) both use exact dynamic programming over the full joint distribution of dice outcomes.

**Ranged sequence:**
1. Per-die probabilities adjusted for Ceaseless / Relentless / Lethal
2. Balanced handled at pool level via convolution of (A−1) normal dice + 1 enhanced die
3. Post-roll: Rending converts a normal to a crit if any crit exists; Severe converts a normal to a crit if no crits exist
4. Defense dice rolled; AP reduces the pool; cover saves bypass rolling
5. Resolution: crit saves cancel crits first, excess become normal saves, then normals; remaining dice deal damage; Devastating X adds mortal wounds per unblocked crit

**Fight sequence:**
1. Both sides roll their melee attack dice (same Balanced/Rending/Severe rules apply)
2. Alternate strike/block actions; strategy (All Attack / Minimize Damage / Optimal) selects the action each turn
3. HP is tracked — if a fighter's wounds drop to 0 mid-fight their remaining dice are forfeited

### Weapon rules reference

| Rule | Effect |
|------|--------|
| Ceaseless | ~1/6 chance to re-roll one die (approximated as ×7/6 on successes) |
| Relentless | Re-roll all misses per die |
| Balanced | Re-roll one die (pool-level; modelled as convolution) |
| Rending | If any crit retained, convert one normal hit to a crit |
| Severe | If no crits retained, convert one normal hit to a crit |
| Lethal 5+/4+ | Lowers the crit threshold |
| Devastating X | +X mortal wounds per retained crit, even if that crit is blocked or saved |
| Torrent | Treat BS as 2+ (near-automatic hits) |
| Brutal | Opponent may only block with crit dice |
| Piercing X | Removes X defense dice (ranged only) |

### Fight strategies

| Strategy | Description |
|----------|-------------|
| All Attack | Always strike with the highest-value die available |
| Minimize Damage | Block greedily — prefer eliminating opponent dice over dealing damage |
| Optimal | Picks whichever action maximizes net damage advantage (damage dealt minus damage taken) |

### Multiblock

When an operative has the Multiblock special rule, one die can cancel two opponent dice:

| Die used | Blocks |
|----------|--------|
| 1 normal | 2 opponent normals |
| 1 crit | 2 opponent crits |
| 1 crit | 1 opponent crit + 1 opponent normal |
| 1 crit | 2 opponent normals |

## File structure

| File | Role |
|------|------|
| `template.html` | Source — edit this, not `killteam.html` |
| `killteam.html` | Generated output; overwritten on every build |
| `build.py` | PDF parser + injector |
| `pyproject.toml` | uv project manifest |
| `uv.lock` | Locked dependency versions |
| `source/*.pdf` | GW datacards; add PDFs here and rebuild |

## Adding a team manually

Find the `/*TEAMS_DATA_PLACEHOLDER*/` comment in `template.html` and add a new entry following the existing schema, then rebuild.

## Parser limitations

- Weapon rules that wrap across PDF lines are recovered by a continuation heuristic
- Equipment and ploy effects are not auto-parsed — add them manually to the team data
- Non-standard weapon names may be misclassified as ranged; add keywords to `MELEE_KEYWORDS` in `build.py` to fix
