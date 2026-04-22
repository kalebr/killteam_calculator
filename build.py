"""
Kill Team Calculator — PDF build script (KT 2024 Void War format)
Usage:
  python build.py                          # parse all PDFs in source/, write index.html
  python build.py --pdf source/team.pdf    # parse a single PDF, write index.html
  python build.py --dump                   # print extracted JSON to stdout only
"""

import argparse
import json
import re
import sys
from pathlib import Path


def _import_pdfplumber():
    try:
        import pdfplumber
        return pdfplumber
    except ImportError:
        sys.exit("pdfplumber not installed. Run: pip install pdfplumber")


# ──────────────────────────────────────────────────
# KT 2024 RULE MAPPING
# Map PDF text rules to calculator rule IDs
# ──────────────────────────────────────────────────

RULE_MAP = {
    'ceaseless':        'ceaseless',
    'relentless':       'relentless',
    'balanced':         'balanced',
    'rending':          'rending',
    'severe':           'severe',
    'brutal':           'brutal',
    'lethal 5+':        'lethal5',
    'lethal 4+':        'lethal4',
    'lethal 6+':        'lethal6',
    'torrent':          'torrent',
    'piercing 1':       'ap1',
    'piercing 2':       'ap2',
    'piercing 3':       'ap3',
    'piercing crits 1': 'ap1',
    'piercing crits 2': 'ap2',
    'devastating 1':    'mw1',
    'devastating 2':    'mw2',
    'devastating 3':    'mw3',
    'devastating 4':    'mw4',
    'devastating 5':    'mw5',
    # Informational only (no damage effect)
    'heavy':            'heavy',
    'stun':             'stun',
    'saturate':         'saturate',
    'silent':           'silent',
    'seek':             'seek',
    'hot':              'hot',
    'shock':            'shock',
    'indirect':         'indirect',
    'tangle':           'tangle',
    'seek light':       'seek_light',
}

SORTED_RULE_KEYS = sorted(RULE_MAP.keys(), key=len, reverse=True)

MELEE_KEYWORDS = {
    'sword', 'blade', 'blades', 'fist', 'claw', 'talon', 'hammer', 'axe',
    'maul', 'knife', 'dagger', 'staff', 'spear', 'whip', 'flail',
    'agoniser', 'chainblade', 'chainsaw', 'chainsword', 'choppa', 'glaive',
    'sculptors', 'razorflail', 'array of blades',
    'close combat', 'power weapon', 'power fist',
    'thunder hammer', 'lightning claw', 'force sword', 'force axe',
    'force stave', 'venom blade', 'halberd', 'trident',
    'stikka', 'klaw', 'big choppa', 'klaws', 'buzzsaw', 'ripping claw',
}


def extract_rules(wr_text: str) -> tuple[list[str], str]:
    rules = []
    lower = wr_text.lower()
    # Fix common OCR artifacts: single letter separated from rest of word
    lower = re.sub(r'\b([a-z])\s+([a-z]{2,})\b', lambda m: m.group(1) + m.group(2), lower)
    lower = re.sub(r'\s*\d+"\s*', ' ', lower)
    lower = re.sub(r'\s*range\s*[\d"]+\s*', ' range ', lower)

    for key in SORTED_RULE_KEYS:
        if key in lower:
            rules.append(RULE_MAP[key])
            lower = lower.replace(key, ' ')

    return list(dict.fromkeys(rules)), wr_text


def is_ranged(weapon_name: str, wr_text: str) -> bool:
    name_lower = weapon_name.lower()
    wr_lower = wr_text.lower()
    if 'range' in wr_lower or re.search(r'\d+"', wr_lower):
        return True
    for kw in MELEE_KEYWORDS:
        if kw in name_lower:
            return False
    return True


def slug(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


# ──────────────────────────────────────────────────
# PARSING — KT 2024 block format
# ──────────────────────────────────────────────────

RE_STAT_HEADER = re.compile(r'APL\s+MOVE\s+SAVE\s+WOUNDS', re.IGNORECASE)
RE_STAT_LINE   = re.compile(r'^(\d+)\s+[\d.]+["\']\s+(\d+)\+\s+(\d+)', re.MULTILINE)
RE_WEAPON_HDR  = re.compile(r'NAME\s+ATK\s+HIT\s+DMG\s+WR', re.IGNORECASE)
RE_WEAPON_LINE = re.compile(r'^(.+?)\s{1,}(\d+)\s+(\d+)\+\s+(\d+)/(\d+)\s+(.*)$')
RE_TEAM_NAME   = re.compile(
    r'^([A-Z][A-Z\s\'"]+?)\s*,\s*(?:IMPERIUM|CHAOS|AELDARI|TYRANID|ORK|NECRON|TAU|CHAOS SPACE|ADEPTUS|CHAOS DAEMON)',
    re.MULTILINE
)


def parse_block(cell_text: str, default_team_name: str) -> tuple[dict | None, str | None]:
    if not RE_STAT_HEADER.search(cell_text):
        return None, None

    lines = [l.strip() for l in cell_text.strip().split('\n') if l.strip()]

    stat_hdr_idx = next((i for i, l in enumerate(lines) if RE_STAT_HEADER.search(l)), None)
    if stat_hdr_idx is None:
        return None, None

    if stat_hdr_idx + 1 >= len(lines):
        return None, None
    op_name = lines[stat_hdr_idx + 1].strip()

    stats = None
    for i in range(stat_hdr_idx + 2, min(stat_hdr_idx + 4, len(lines))):
        m = RE_STAT_LINE.match(lines[i])
        if m:
            stats = {'apl': int(m.group(1)), 'sv': int(m.group(2)), 'w': int(m.group(3))}
            break

    if not stats:
        return None, None

    team_name = default_team_name
    for line in reversed(lines):
        tm = RE_TEAM_NAME.match(line)
        if tm:
            team_name = tm.group(1).strip().title()
            break

    weapons = []
    wpn_hdr_idx = next((i for i, l in enumerate(lines) if RE_WEAPON_HDR.search(l)), None)
    if wpn_hdr_idx is not None:
        last_weapon = None
        for line in lines[wpn_hdr_idx + 1:]:
            if RE_STAT_HEADER.search(line):
                break
            if len(line) > 6 and line.isupper():
                break
            m = RE_WEAPON_LINE.match(line)
            if m:
                name, a_str, hit_str, d_str, crit_str, wr_str = m.groups()
                name = name.strip()
                wr_str = wr_str.strip().strip('-').strip()
                a, skill, d, crit_d = int(a_str), int(hit_str), int(d_str), int(crit_str)
                rules, _ = extract_rules(wr_str)
                wtype = 'melee' if not is_ranged(name, wr_str) else 'ranged'
                w = {
                    'id': slug(name) + '_' + wtype[:5],
                    'name': name, 'type': wtype,
                    'a': a, 'skill': skill, 'd': d, 'crit_d': crit_d,
                    'rules': rules
                }
                weapons.append(w)
                last_weapon = w
            elif last_weapon and not re.search(r'\d+\s*\+', line):
                extra, _ = extract_rules(line)
                for r in extra:
                    if r not in last_weapon['rules']:
                        last_weapon['rules'].append(r)

    op = {
        'id': slug(op_name),
        'name': op_name.title(),
        'df': 3,
        'sv': stats['sv'],
        'w': stats['w'],
        'weapons': weapons
    }
    return op, team_name


def parse_pdf(pdf_path: Path) -> dict | None:
    pdfplumber = _import_pdfplumber()
    default_name = pdf_path.stem.replace('_', ' ').replace('-', ' ').title()

    operatives_by_id: dict[str, dict] = {}
    team_name = default_name

    try:
        with pdfplumber.open(pdf_path) as pdf:
            cell_texts = []
            for page in pdf.pages:
                tables = page.extract_tables() or []
                for table in tables:
                    for row in table:
                        for cell in row:
                            if cell and isinstance(cell, str) and len(cell) > 20:
                                cell_texts.append(cell)

            for cell in cell_texts:
                op, tname = parse_block(cell, default_name)
                if op and op['id'] not in operatives_by_id:
                    operatives_by_id[op['id']] = op
                    if tname and tname != default_name:
                        team_name = tname

    except Exception as e:
        print(f"  WARNING: Error parsing {pdf_path.name}: {e}", file=sys.stderr)
        return {
            'name': default_name,
            'MANUAL_REVIEW': True,
            'parse_error': str(e),
            'operatives': [],
        }

    operatives = list(operatives_by_id.values())

    if not operatives:
        print(f"  WARNING: No operatives found in {pdf_path.name}", file=sys.stderr)
        return {
            'name': team_name,
            'MANUAL_REVIEW': True,
            'operatives': [],
        }

    operatives.sort(key=lambda o: (-len(o['weapons']), o['name']))

    return {
        'name': team_name,
        'operatives': operatives,
    }


# ──────────────────────────────────────────────────
# SEED DATA (used when no PDFs are in source/)
# ──────────────────────────────────────────────────

SEED_DATA = {
    "version": "1.0",
    "teams": {
        "intercession_squad": {
            "name": "Intercession Squad (Example)",
            "operatives": [
                {
                    "id": "intercessor_sergeant",
                    "name": "Intercessor Sergeant",
                    "df": 3, "sv": 3, "w": 15,
                    "weapons": [
                        {"id": "bolt_rifle_ranged", "name": "Bolt Rifle", "type": "ranged",
                         "a": 4, "skill": 3, "d": 3, "crit_d": 4, "rules": ["ap1"]},
                        {"id": "chainsword_melee", "name": "Chainsword", "type": "melee",
                         "a": 5, "skill": 3, "d": 4, "crit_d": 5, "rules": []}
                    ]
                },
                {
                    "id": "intercessor_warrior",
                    "name": "Intercessor Warrior",
                    "df": 3, "sv": 3, "w": 14,
                    "weapons": [
                        {"id": "bolt_rifle_ranged", "name": "Bolt Rifle", "type": "ranged",
                         "a": 4, "skill": 3, "d": 3, "crit_d": 4, "rules": ["ap1"]},
                        {"id": "auto_bolt_rifle_ranged", "name": "Auto Bolt Rifle", "type": "ranged",
                         "a": 4, "skill": 3, "d": 3, "crit_d": 4, "rules": ["torrent"]},
                        {"id": "fists_melee", "name": "Fists", "type": "melee",
                         "a": 4, "skill": 3, "d": 3, "crit_d": 4, "rules": []}
                    ]
                }
            ],
        },
        "kommando": {
            "name": "Kommando (Example)",
            "operatives": [
                {
                    "id": "kommando_boss",
                    "name": "Kommando Boss",
                    "df": 3, "sv": 5, "w": 10,
                    "weapons": [
                        {"id": "slugga_ranged", "name": "Slugga", "type": "ranged",
                         "a": 3, "skill": 4, "d": 3, "crit_d": 4, "rules": []},
                        {"id": "choppa_melee", "name": "Choppa", "type": "melee",
                         "a": 5, "skill": 3, "d": 3, "crit_d": 4, "rules": ["rending"]}
                    ]
                }
            ],
        }
    }
}


# ──────────────────────────────────────────────────
# BUILD
# ──────────────────────────────────────────────────

def build(pdf_paths: list[Path], template_path: Path, output_path: Path, dump: bool = False):
    if pdf_paths:
        print(f"Parsing {len(pdf_paths)} PDF(s)...")
        teams = {}
        for p in pdf_paths:
            print(f"  -> {p.name}")
            result = parse_pdf(p)
            if result:
                tid = slug(result['name'])
                teams[tid] = result
                status = "! MANUAL_REVIEW" if result.get('MANUAL_REVIEW') else "OK"
                ops = len(result.get('operatives', []))
                print(f"     {status}  {result['name']}  ({ops} operative(s))")
        data = {"version": "1.0", "teams": teams}
    else:
        print("No PDFs in source/ - using built-in seed data (example teams).")
        data = SEED_DATA

    if dump:
        print(json.dumps(data, indent=2))
        return

    template = template_path.read_text(encoding='utf-8')
    js_blob = f"const TEAMS_DATA = {json.dumps(data, indent=2)};"
    output_html = template.replace('/*TEAMS_DATA_PLACEHOLDER*/', js_blob)
    output_path.write_text(output_html, encoding='utf-8')
    size_kb = output_path.stat().st_size // 1024
    print(f"\nWrote: {output_path}  ({size_kb} KB)")
    print("Open index.html directly in any browser - no web server needed.")


def main():
    root = Path(__file__).parent
    template = root / 'template.html'
    output   = root / 'index.html'
    source   = root / 'source'

    parser = argparse.ArgumentParser(description='Kill Team Calculator build script')
    parser.add_argument('--pdf', help='Path to a single PDF file')
    parser.add_argument('--dump', action='store_true', help='Print JSON to stdout only')
    args = parser.parse_args()

    if not template.exists():
        sys.exit(f"template.html not found at {template}")

    if args.pdf:
        pdf_paths = [Path(args.pdf)]
    else:
        pdf_paths = sorted(source.glob('*.pdf')) if source.exists() else []

    build(pdf_paths, template, output, dump=args.dump)


if __name__ == '__main__':
    main()
