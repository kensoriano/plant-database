"""Import the plant spreadsheet into schema.sql and index.html.

Usage:
    python3 scripts/import_spreadsheet.py path/to/Plant_Data_Base.xlsx

Reads Sheet1 of the workbook, cleans each row, merges duplicate plants, and
rewrites the generated sections of schema.sql (between the BEGIN/END
GENERATED PLANT DATA lines) and index.html (the PLANTS list). Prints a short
report of anything it had to guess at or couldn't map.

Rules (agreed with the database owner):
  - Unchecked boxes mean "unknown", stored as NULL, not "no".
  - Blank cells and the sheet's "(1) Category" default are treated as empty.
  - Botanical names follow USDA PLANTS formatting: genus capitalized, epithets
    lowercase, hybrid sign attached (Calamagrostis ×acutiflora), 'ssp.' and
    'var.', cultivars in single quotes. Spelling fixes and synonyms are listed
    in NAME_FIXES below.
  - Bloom seasons become month ranges using SEASON_MONTHS below.

Needs openpyxl (pip install openpyxl).
"""

import json
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schema.sql"
PREVIEW = ROOT / "index.html"

# Sheet column headers, as they appear in row 1
COL = {
    "name": "Botanic Name", "common": "Common Name", "height": "Height", "width": "Width",
    "native": "Native", "form": "Form", "deer": "Deer Resistant", "birds": "Bird Attraction",
    "butterflies": "Butterfly Attraction", "bees": "Bee Attraction", "comments": "Comments",
    "hummingbirds": "Hummingbird Attraction", "soil1": "Soil Type", "fall": "Fall Color",
    "toxic": "Toxic", "flower": "Flower Color", "soil2": "Soil Type 2", "bioswale": "Bio-swale",
    "bloom": "Time of Flowering", "disease": "Good Disease Resistance",
    "light": "Light Requirements", "interest": "Seasonal Interest", "foliage": "Foliage",
    "zone": "Zone", "pollutants": "Tolerant to Pollutants",
}

# ---------------------------------------------------------------------------
# Botanical names
# ---------------------------------------------------------------------------

# Exact sheet name (whitespace collapsed) -> (cleaned name, synonyms or None).
# Spelling corrections and messy entries only; the general formatting rules in
# format_name() handle capitalization and hybrid signs.
NAME_FIXES = {
    "Asarum canadensis": ("Asarum canadense", None),
    "Astilbe 'Europa' (japonica Europa)": ("Astilbe japonica 'Europa'", None),
    "Calamagrostis x acutiflora 'Karlfoerster'": ("Calamagrostis ×acutiflora 'Karl Foerster'", None),
    "Chelone oblique": ("Chelone obliqua", None),
    "Cornus Stolonifera (Cornus sericea 'Cardinal')": ("Cornus sericea 'Cardinal'", "Cornus stolonifera 'Cardinal'"),
    "Crataegus spp": ("Crataegus spp.", None),
    "Geranium Oxonianum \"Claridge Druce'": ("Geranium ×oxonianum 'Claridge Druce'", None),
    "Hakonechloa macra 'Albo-Straita'": ("Hakonechloa macra 'Albostriata'", None),
    "Helleborus Orientalis-Hybrids 'Pink Lady'": ("Helleborus ×hybridus 'Pink Lady'", "Helleborus orientalis hybrids"),
    "Iris Sibirica 'Caeser's Brother'": ("Iris sibirica 'Caesar's Brother'", None),
    "Juniperus Chinensis Sargentii": ("Juniperus chinensis var. sargentii", None),
    "Liriodendron Tulipfera": ("Liriodendron tulipifera", None),
    "Molinia Litorialis 'Windspiel'": ("Molinia litoralis 'Windspiel'", None),
    "Monarda 'Fistulosa'": ("Monarda fistulosa", None),
    "Prunus blireiana": ("Prunus ×blireana", None),
    "Rudbeckia Fulgida 'Goldstrum'": ("Rudbeckia fulgida 'Goldsturm'", None),
    "Sarcococca Hookerana 'Humilis'": ("Sarcococca hookeriana var. humilis", None),
    "Scirpus pungens (Schoenoplectus pungens)": ("Scirpus pungens", "Schoenoplectus pungens"),
    "Solidago 'Little Lemmon'": ("Solidago 'Little Lemon'", None),
    "Sporobolus heterolepsis": ("Sporobolus heterolepis", None),
    "Styrax Japonica": ("Styrax japonicus", None),
    "Veronica ssp. Incana 'Sunny Border Blue'": ("Veronica 'Sunny Border Blue'", None),
    "Aster x Frikartii 'Monch'": ("Aster ×frikartii 'Mönch'", None),
}

SMALL_WORDS = {"de", "and", "of", "la"}


def format_name(raw):
    """Apply USDA-style formatting to a botanical name. Returns (name, synonyms)."""
    raw = re.sub(r"\s+", " ", raw).strip()
    if raw in NAME_FIXES:
        return NAME_FIXES[raw]
    raw = raw.replace('"', "'")
    # Split off the cultivar (everything from the first quote on)
    q = raw.find("'")
    base, cultivar = (raw[:q].strip(), raw[q:]) if q >= 0 else (raw, "")
    words = []
    hybrid = False
    for i, w in enumerate(base.split()):
        lw = w.lower()
        if lw in ("x", "×"):
            hybrid = True
            continue
        if lw in ("subsp.", "ssp."):
            w = "ssp."
        elif lw == "var.":
            w = "var."
        elif not words:
            w = w[:1].upper() + w[1:].lower()  # genus
        else:
            w = lw
        if hybrid:
            w = "×" + w
            hybrid = False
        words.append(w)
    name = " ".join(words)
    if cultivar:
        inner = cultivar.strip("' ")
        parts = []
        for j, w in enumerate(inner.split()):
            if j and w.lower() in SMALL_WORDS:
                parts.append(w.lower())
            else:
                parts.append(w[:1].upper() + w[1:])
        name += " '" + " ".join(parts) + "'"
    return name, None


def format_common(raw):
    """Clean a common name: one line, comma-separated, title case on word starts."""
    if not raw:
        return None, None
    names = [n.strip(" ,") for n in re.split(r"[\n,]", raw) if n.strip(" ,")]

    def tc(n):
        return " ".join(w[:1].upper() + w[1:] for w in n.split())

    names = [tc(n) for n in names]
    return names[0], (", ".join(names[1:]) or None)


# ---------------------------------------------------------------------------
# Value parsers
# ---------------------------------------------------------------------------


def blank(v):
    if v is None:
        return None
    v = str(v).strip()
    return None if v in ("", "(1) Category") else v


def parse_size(raw, report, name, what):
    """'2-3'' / '1' - 1.5'' / '6-12"' / '30"' / '40-100'+' -> (min_in, max_in)."""
    raw = blank(raw)
    if not raw:
        return None, None
    nums = [float(n) for n in re.findall(r"\d*\.?\d+", raw)]
    if not nums:
        report.append(f"{name}: couldn't read {what} {raw!r}")
        return None, None
    # Use the last unit written anywhere in the cell; default to feet.
    units = re.findall(r"['\"]", raw)
    if not units:
        report.append(f"{name}: {what} {raw!r} has no unit, read as feet")
    factor = 1 if units and units[-1] == '"' else 12
    lo, hi = nums[0] * factor, nums[-1] * factor
    return round(lo, 1), round(hi, 1)


def parse_zone(raw, report, name):
    raw = blank(raw)
    if not raw:
        return None, None
    nums = [int(n) for n in re.findall(r"\d+", raw)]
    if raw.lower().startswith("hardy to zone 0"):
        report.append(f"{name}: zone {raw!r} stored as zone 1 (the coldest USDA zone)")
        return 1, None
    if len(nums) == 1:
        return nums[0], None  # 'hardy to' a single zone; no upper limit given
    return nums[0], nums[-1]


SUN_MAP = {
    "full sun/ partial shade": ["Full Sun", "Part Shade"],
    "full sun/partial shade": ["Full Sun", "Part Shade"],
    "full sun/partial sun": ["Full Sun", "Part Shade"],
    "full sun": ["Full Sun"],
    "partial shade": ["Part Shade"],
    "partial sun": ["Part Shade"],
    "morning sun/ afternoon shade": ["Part Shade"],
    "full shade/ partial sun": ["Part Shade", "Shade"],
    "full shade": ["Shade"],
    "shade/sun": ["Full Sun", "Part Shade", "Shade"],
}

MOISTURE_ORDER = ["Dry", "Medium", "Moist", "Wet"]
# Words in the soil columns -> moisture levels
MOISTURE_WORDS = [
    (r"\bdry\b|drought|rocky", "Dry"),
    (r"\bmedium\b|\baverage\b|\bnormal\b|well drained", "Medium"),
    (r"\bmoist|humusy|organic", "Moist"),
    (r"\bwet\b|saturated|wetland", "Wet"),
]
SOIL_CONDITION_WORDS = [
    (r"well drained", "Well Drained"),
    (r"humus|organic|\brich\b|ruch", "Humus-Rich"),
    (r"fertile", "Fertile"),
    (r"loam", "Loamy"),
    (r"sand", "Sandy"),
    (r"clay", "Clay"),
    (r"rocky|grave", "Rocky"),
    (r"acidic", "Acidic"),
    (r"neutral", "Neutral pH"),
]


def parse_soil(texts):
    moist, cond = set(), set()
    for t in texts:
        lt = t.lower()
        found = [lvl for pat, lvl in MOISTURE_WORDS if re.search(pat, lt)]
        # "X to Y" ranges cover every level in between, e.g. "Medium to wet"
        if found and re.search(r"\bto\b|-", lt):
            idx = [MOISTURE_ORDER.index(f) for f in found]
            found = MOISTURE_ORDER[min(idx):max(idx) + 1]
        moist.update(found)
        cond.update(c for pat, c in SOIL_CONDITION_WORDS if re.search(pat, lt))
    return [m for m in MOISTURE_ORDER if m in moist], sorted(cond)


# Season words -> (start month, end month)
SEASON_MONTHS = [
    ("late winter", (2, 2)), ("early spring", (3, 4)), ("late spring", (5, 6)),
    ("early summer", (6, 6)), ("mid to late summer", (7, 9)), ("late summer", (8, 9)),
    ("early fall", (9, 9)), ("late fall", (10, 11)),
    ("spring", (4, 5)), ("summer", (6, 8)), ("fall", (9, 10)), ("winter", (12, 2)),
]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]


def parse_bloom(raw, report, name):
    """'Late Spring - Summer' -> (5, 8). Returns (start, end) or (None, None)."""
    raw = blank(raw)
    if not raw or raw.lower() == "doesn't flower":
        return None, None
    hits = []  # (position in text, (start, end))
    lt = raw.lower()
    taken = [False] * len(lt)
    for word, rng in SEASON_MONTHS:
        for m in re.finditer(word, lt):
            if not any(taken[m.start():m.end()]):
                hits.append((m.start(), rng))
                for k in range(m.start(), m.end()):
                    taken[k] = True
    for i, mon in enumerate(MONTHS):
        for m in re.finditer(mon, lt):
            if not any(taken[m.start():m.end()]):
                hits.append((m.start(), (i + 1, i + 1)))
    if not hits:
        report.append(f"{name}: couldn't read bloom time {raw!r}")
        return None, None
    hits.sort()
    return hits[0][1][0], hits[-1][1][1]


# First color named in the flower color cell -> representative hex.
# Longer names are checked first, so 'pale yellow' wins over 'yellow'.
COLOR_HEX = {
    "silver-white": "#E6E6DE", "silvery-pink": "#E8C3CF", "pinkish white": "#F3D9E2", "greenish white": "#E2EBCF",
    "whitish yellow": "#F1E7A8", "pale yellow": "#F3E59A", "greenish yellow": "#C8D45A",
    "yellowish green": "#C8D45A", "yellow-green": "#C8D45A", "orange red": "#E0582B",
    "deep red": "#9E1B2A", "rose red": "#C2385A", "rose pink": "#E37B9A",
    "rose-purple": "#A0479A", "rosy purple": "#A0479A", "clear pink": "#F0A6C0",
    "pinkish-purple": "#B0559A", "redish purple": "#8E2F6B", "purplish-red": "#9C2E54",
    "redish brown": "#8B4A35", "chocolate-purple": "#5A2E3A", "lavender blue": "#9AA3DE",
    "steel blue": "#4682B4", "deep blue": "#2F4A9E", "purple tinted": "#9C7BB8",
    "cream": "#EFE6C8", "white": "#F5F3EA", "yellow": "#F2C94C", "gold": "#D9A520",
    "orange": "#E8862A", "crimson": "#B3203A", "red": "#C8323C", "pinkish": "#EBB3C6",
    "pink": "#E79AB5", "lavender": "#B49BD6", "lilac": "#C3A3D9", "violet": "#7E57C2",
    "purple": "#7B4FA8", "blue": "#4F6FC4", "green": "#8DB255", "brown": "#8B6B4A",
}


def color_hex(raw, report, name):
    raw = blank(raw)
    if not raw or raw.lower() == "no flowers":
        return None
    lt = raw.lower().strip("' .")
    for key in sorted(COLOR_HEX, key=len, reverse=True):
        if lt.startswith(key):
            return COLOR_HEX[key]
    report.append(f"{name}: no color match for {raw!r}")
    return None


SEASONS = ["Spring", "Summer", "Fall", "Winter"]


def parse_interest(raw):
    raw = blank(raw)
    if not raw:
        return []
    if "all seasons" in raw.lower():
        return SEASONS[:]
    return [s for s in SEASONS if s.lower() in raw.lower()]


TYPE_MAP = {"Grass/Perennial": "Grass", "Perennial Herb": "Perennial"}
# Plants whose duplicate rows disagreed on type
TYPE_OVERRIDES = {"Hypericum calycinum": "Groundcover", "Sarcococca hookeriana var. humilis": "Shrub"}


def parse_native(raw):
    raw = blank(raw)
    return {"Yes": "Yes", "-1": "Yes", "No": "No", "0": "No"}.get(raw)


def parse_toxic(raw):
    raw = blank(raw)
    if not raw:
        return None, None
    if raw.lower() in ("no", "none"):
        return 0, None
    return 1, raw


def parse_foliage(raw):
    raw = blank(raw)
    if not raw:
        return None
    return "Semi-Evergreen" if raw.lower().startswith("semi") else raw


# ---------------------------------------------------------------------------
# Rows -> plants
# ---------------------------------------------------------------------------

LIST_FIELDS = ("sun", "moisture", "soil", "wildlife", "uses", "interest")


def read_rows(path, report):
    ws = openpyxl.load_workbook(path, data_only=True)["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))
    head = {h: i for i, h in enumerate(rows[0])}
    plants = []
    for r in rows[1:]:
        def g(key):
            return r[head[COL[key]]]

        if not blank(g("name")):
            continue
        name, syn = format_name(str(g("name")))
        common, other = format_common(blank(g("common")))
        soil_texts = [t for t in (blank(g("soil1")), blank(g("soil2"))) if t]
        moisture, soil = parse_soil(soil_texts)
        hmin, hmax = parse_size(g("height"), report, name, "height")
        smin, smax = parse_size(g("width"), report, name, "width")
        zmin, zmax = parse_zone(g("zone"), report, name)
        bs, be = parse_bloom(g("bloom"), report, name)
        tox, toxn = parse_toxic(g("toxic"))
        light = blank(g("light"))
        if light and light.lower() not in SUN_MAP:
            report.append(f"{name}: couldn't read light {light!r}")
        plants.append({
            "name": name, "synonyms": syn, "common": common, "other_common": other,
            "type": TYPE_MAP.get(g("form"), g("form")),
            "hmin": hmin, "hmax": hmax, "smin": smin, "smax": smax,
            "zmin": zmin, "zmax": zmax,
            # Checked -> 1, unchecked -> None (unknown)
            "deer": 1 if g("deer") else None,
            "pollutant": 1 if g("pollutants") else None,
            "bioswale": 1 if g("bioswale") else None,
            "disease": 1 if g("disease") else None,
            "toxic": tox, "toxicity_notes": toxn,
            "native": parse_native(g("native")),
            "foliage": parse_foliage(g("foliage")),
            "bs": bs, "be": be,
            "hex": color_hex(g("flower"), report, name) if bs else None,
            "bloom_notes": blank(g("bloom")),
            "flower_color": blank(g("flower")),
            "fall_color": blank(g("fall")),
            "soil_notes": "; ".join(soil_texts) or None,
            "comments": blank(g("comments")),
            "sun": SUN_MAP.get((light or "").lower(), []),
            "moisture": moisture, "soil": soil,
            "wildlife": [w for k, w in (("bees", "Bees"), ("butterflies", "Butterflies"),
                                        ("birds", "Birds"), ("hummingbirds", "Hummingbirds")) if g(k)],
            "uses": ["Bioretention"] if g("bioswale") else [],
            "interest": parse_interest(g("interest")),
        })
    return plants


def merge(plants, report):
    """Merge rows with the same botanical name: the most filled-in row wins, lists combine."""
    out = {}
    filled = lambda p: sum(1 for v in p.values() if v not in (None, []))
    for p in sorted(plants, key=filled, reverse=True):
        key = p["name"].lower()
        if key not in out:
            out[key] = p
            continue
        a = out[key]
        conflicts = []
        for k, v in p.items():
            if k in LIST_FIELDS:
                a[k] = a[k] + [x for x in v if x not in a[k]]
            elif a[k] is None:
                a[k] = v
            elif v is not None and v != a[k]:
                if k == "common":
                    extra = [n for n in [v] + (p["other_common"] or "").split(", ") if n]
                    have = [n for n in (a["other_common"] or "").split(", ") if n]
                    a["other_common"] = ", ".join(have + [n for n in extra if n not in have and n != a["common"]]) or None
                elif k in ("comments", "soil_notes"):
                    a[k] = a[k] + ("; " if k == "soil_notes" else " ") + v
                elif k != "other_common":
                    conflicts.append(f"{k}: kept {a[k]!r} over {v!r}")
        report.append(f"merged duplicate {p['name']}" + (" (" + "; ".join(conflicts) + ")" if conflicts else ""))
    for a in out.values():
        a["type"] = TYPE_OVERRIDES.get(a["name"], a["type"])
    return sorted(out.values(), key=lambda p: p["name"].lower())


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def sql(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v).is_integer() else str(v)
    return "'" + str(v).replace("'", "''") + "'"


PLANT_COLS = [
    ("botanical_name", "name"), ("common_name", "common"), ("other_common_names", "other_common"),
    ("synonyms", "synonyms"), ("plant_type", "type"), ("foliage_type", "foliage"),
    ("height_min_in", "hmin"), ("height_max_in", "hmax"), ("spread_min_in", "smin"),
    ("spread_max_in", "smax"), ("zone_min", "zmin"), ("zone_max", "zmax"),
    ("deer_resistant", "deer"), ("pollutant_tolerant", "pollutant"),
    ("bioswale_suitable", "bioswale"), ("disease_resistant", "disease"), ("toxic", "toxic"),
    ("toxicity_notes", "toxicity_notes"), ("native_as_entered", "native"),
    ("bloom_start_month", "bs"), ("bloom_end_month", "be"), ("bloom_color_hex", "hex"),
    ("bloom_time_notes", "bloom_notes"), ("flower_color", "flower_color"),
    ("fall_color", "fall_color"), ("soil_notes", "soil_notes"), ("comments", "comments"),
]

# (junction table, lookup table, lookup id column, plant field)
LINKS = [
    ("plant_sun_exposure", "sun_exposure", "sun_exposure_id", "sun"),
    ("plant_soil_moisture", "soil_moisture", "soil_moisture_id", "moisture"),
    ("plant_soil_condition", "soil_condition", "soil_condition_id", "soil"),
    ("plant_wildlife_value", "wildlife_value", "wildlife_value_id", "wildlife"),
    ("plant_landscape_use", "landscape_use", "landscape_use_id", "uses"),
    ("plant_seasonal_interest", "season", "season_id", "interest"),
]


def build_sql(plants):
    cols = [c for c, _ in PLANT_COLS]
    out = [f"-- {len(plants)} plants. Plant type and foliage are looked up by name.",
           "WITH v(" + ", ".join(cols) + ") AS (VALUES"]
    out.append(",\n".join(" (" + ", ".join(sql(p[k]) for _, k in PLANT_COLS) + ")" for p in plants))
    plain = [c for c in cols if c not in ("plant_type", "foliage_type")]
    out.append(")\nINSERT INTO plant (" + ", ".join(plain) + ", plant_type_id, foliage_type_id)\n"
               "SELECT " + ", ".join("v." + c for c in plain) + ",\n"
               "       (SELECT plant_type_id FROM plant_type WHERE name = v.plant_type),\n"
               "       (SELECT foliage_type_id FROM foliage_type WHERE name = v.foliage_type)\n"
               "FROM v;\n")
    for table, lookup, idcol, field in LINKS:
        pairs = [(p["name"], x) for p in plants for x in p[field]]
        if not pairs:
            continue
        out.append(f"WITH v(botanical_name, value) AS (VALUES\n" +
                   ",\n".join(f" ({sql(a)}, {sql(b)})" for a, b in pairs) +
                   f")\nINSERT INTO {table} (plant_id, {idcol})\n"
                   f"SELECT p.plant_id, l.{idcol}\n"
                   f"FROM v JOIN plant p ON p.botanical_name = v.botanical_name\n"
                   f"       JOIN {lookup} l ON l.name = v.value;\n")
    return "\n".join(out)


def build_js(plants):
    rows = []
    for p in plants:
        o = {
            "b": p["name"], "c": p["common"], "c2": p["other_common"], "syn": p["synonyms"],
            "t": p["type"], "hmin": p["hmin"], "hmax": p["hmax"], "smin": p["smin"],
            "smax": p["smax"], "z": [p["zmin"], p["zmax"]], "sun": p["sun"], "m": p["moisture"],
            "deer": p["deer"], "bio": p["bioswale"], "pol": p["pollutant"], "dis": p["disease"],
            "tox": p["toxic"], "toxn": p["toxicity_notes"], "nat": p["native"],
            "fol": p["foliage"], "bs": p["bs"], "be": p["be"], "col": p["hex"],
            "bt": p["bloom_notes"], "fc": p["flower_color"], "fall": p["fall_color"],
            "soil": p["soil"], "wl": p["wildlife"], "use": p["uses"], "si": p["interest"],
            "note": p["comments"],
        }
        for k in ("hmin", "hmax", "smin", "smax"):
            if isinstance(o[k], float) and o[k].is_integer():
                o[k] = int(o[k])
        rows.append(json.dumps(o, ensure_ascii=False, separators=(",", ":")))
    return "var PLANTS=[\n" + ",\n".join(rows) + "\n];"


def replace_between(text, start, end, new):
    i, j = text.index(start), text.index(end)
    return text[:i + len(start)] + "\n" + new + "\n" + text[j:]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    report = []
    plants = merge(read_rows(sys.argv[1], report), report)

    s = SCHEMA.read_text()
    SCHEMA.write_text(replace_between(s, "-- BEGIN GENERATED PLANT DATA", "-- END GENERATED PLANT DATA",
                                      build_sql(plants)))
    h = PREVIEW.read_text()
    h = re.sub(r"var PLANTS=\[.*?\n\];", lambda _: build_js(plants), h, count=1, flags=re.S)
    PREVIEW.write_text(h)

    print(f"{len(plants)} plants written to {SCHEMA.name} and {PREVIEW.name}")
    for line in report:
        print(" -", line)


if __name__ == "__main__":
    main()
