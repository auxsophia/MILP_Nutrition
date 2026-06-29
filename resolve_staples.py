"""
resolve_staples.py
------------------
One-shot fix for staple fdc_ids. Name-matches every staple against your REAL
loaded USDA data, scores candidates, picks the best, and writes repertoire.json.

Prints a verification report with kcal/protein snapshots so a wrong match is
obvious. If a choice is wrong, adjust that spec's include/exclude/pin keywords
and re-run. You never touch raw ids.

Special keys per spec:
  pin:     an fdc_id to force (overrides scoring) when you KNOW the right entry
  term:    substring(s) to search (any match)
  include: keywords that boost the right preparation
  exclude: keywords that reject wrong preparations

Run:
    python resolve_staples.py          # writes repertoire.json + report
    python resolve_staples.py --dry    # report only
"""
import sys, json, os
import data_loader as dl

STAPLE_SPECS = [
    # --- GRAINS (weigh dry, use uncooked entries) ---
    {"term": ["spelt"], "include": [], "exclude": ["flour", "bread", "cooked"],
     "label": "Spelt (dry)", "grams": 80, "tags": ["weigh-dry"]},
    {"term": ["oats"], "include": ["regular and quick", "rolled"], "exclude": ["cookie", "bar", "granola", "bread", "fortified", "milk", "QUAKER"],
     "label": "Oats (dry)", "grams": 80, "tags": ["weigh-dry"]},
    {"term": ["barley, hulled"], "include": [], "exclude": ["flour"],
     "label": "Barley (hulled, dry)", "grams": 80, "tags": ["weigh-dry"]},

    # --- LEGUMES ---
    {"term": ["peas, split"], "include": ["mature", "raw"], "exclude": ["cooked", "soup"],
     "label": "Split peas (dry)", "grams": 100, "tags": ["weigh-dry"]},
    {"term": ["peas, green, split"], "include": [], "exclude": ["cooked", "soup"],
     "label": "Green peas (dry)", "grams": 100, "tags": ["weigh-dry"]},
    {"term": ["broadbeans", "fava"], "include": ["mature", "raw"], "exclude": ["cooked", "immature"],
     "label": "Broad beans (dry)", "grams": 100, "tags": ["weigh-dry"]},

    # --- GREENS ---
    {"term": ["spinach, raw"], "include": [], "exclude": ["cooked", "canned", "frozen"],
     "label": "Spinach (raw)", "grams": 60},
    {"term": ["leeks", "(bulb and lower leaf-portion), raw"], "include": ["raw"], "exclude": ["cooked", "freeze"],
     "label": "Leeks (raw)", "grams": 89},
    {"term": ["sorrel", "dock"], "include": ["raw"], "exclude": ["cooked"],
     "label": "Sorrel", "grams": 60},
    {"term": ["kale, raw"], "include": [], "exclude": ["cooked", "frozen", "scotch"],
     "label": "Kale (raw)", "grams": 67},
    {"term": ["cabbage, raw"], "include": [], "exclude": ["cooked", "chinese", "red", "savoy", "napa"],
     "label": "Cabbage (raw)", "grams": 89},
    {"term": ["broccoli, raw"], "include": [], "exclude": ["cooked", "frozen", "leaves", "raab"],
     "label": "Broccoli (brassica)", "grams": 91},

    # --- ROOTS / SEA VEG ---
    {"term": ["beets, raw"], "include": [], "exclude": ["cooked", "canned", "greens"],
     "label": "Beets (raw)", "grams": 82},
    {"term": ["seaweed, kelp", "seaweed, laver"], "include": ["raw"], "exclude": ["dried"],
     "label": "Seaweed (kelp)", "grams": 10},
    {"term": ["parsnips, raw"], "include": [], "exclude": ["cooked"],
     "label": "Parsnips (raw)", "grams": 78},
    {"term": ["carrots, raw"], "include": [], "exclude": ["cooked", "canned", "frozen", "baby", "juice"],
     "label": "Carrots (raw)", "grams": 61},

    # --- FRUITS ---
    {"term": ["apples, raw, with skin"], "include": [], "exclude": ["cooked", "canned", "juice", "dried"],
     "label": "Apple", "grams": 125},
    {"term": ["pears, raw"], "include": [], "exclude": ["canned", "dried", "asian", "juice"],
     "label": "Pear", "grams": 140},
    {"term": ["raspberries, raw"], "include": [], "exclude": ["frozen", "canned"],
     "label": "Raspberries", "grams": 100},
    {"term": ["blackberries, raw"], "include": [], "exclude": ["frozen", "canned"],
     "label": "Blackberries", "grams": 100},
    {"term": ["strawberries, raw"], "include": [], "exclude": ["frozen", "canned"],
     "label": "Strawberries", "grams": 100},
    {"term": ["blueberries, raw"], "include": [], "exclude": ["frozen", "wild", "canned", "dried"],
     "label": "Blueberries", "grams": 100},
    {"term": ["pomegranate", "pomegranates, raw"], "include": ["raw"], "exclude": ["juice"],
     "label": "Pomegranate", "grams": 87},
    {"term": ["cherries, sweet, raw"], "include": [], "exclude": ["canned", "frozen", "sour", "dried", "juice"],
     "label": "Cherries", "grams": 100},

    # --- NUTS ---
    {"term": ["nuts, hazelnuts or filberts"], "include": [], "exclude": ["oil", "flour", "meal", "creamer", "spread", "blanched"],
     "label": "Hazelnuts", "grams": 28},
    {"term": ["nuts, walnuts, english"], "include": [], "exclude": ["oil", "black", "glazed"],
     "label": "Walnuts", "grams": 28},
    {"term": ["nuts, pecans"], "include": [], "exclude": ["oil", "cinnamon", "salt"],
     "label": "Pecans", "grams": 28},
    {"term": ["nuts, almonds, blanched"], "include": ["blanched"], "exclude": ["oil", "flour", "meal", "milk", "butter", "honey", "roasted"],
     "label": "Almonds (blanched)", "grams": 28},

    # --- SEEDS ---
    {"term": ["seeds, chia"], "include": ["dried"], "exclude": [],
     "label": "Chia seeds (dry)", "grams": 24, "tags": ["weigh-dry"]},
    {"term": ["seeds, hemp", "hemp seed"], "include": ["hulled"], "exclude": [],
     "label": "Hemp seeds", "grams": 30},
    {"term": ["seeds, flaxseed"], "include": [], "exclude": ["oil"],
     "label": "Flaxseed (meal)", "grams": 14, "tags": ["weigh-dry"]},

    # --- PROTEIN: fish & shellfish ---
    {"term": ["egg, whole, raw"], "include": ["fresh"], "exclude": ["frozen", "dried", "white", "yolk"],
     "label": "Egg, whole", "grams": 50},
    {"term": ["fish, herring, atlantic"], "include": ["raw"], "exclude": ["cooked", "pickled", "kippered", "oil"],
     "label": "Herring (raw)", "grams": 100},
    {"term": ["fish, sardine, atlantic"], "include": ["oil", "drained"], "exclude": ["tomato"],
     "label": "Sardines (oil, drained)", "grams": 92},
    {"term": ["fish, mackerel, atlantic"], "include": ["raw"], "exclude": ["cooked", "salted", "smoked"],
     "label": "Mackerel (raw)", "grams": 112},
    {"term": ["mollusks, oyster"], "include": ["raw"], "exclude": ["cooked", "canned", "fried", "breaded", "smoked"],
     "label": "Oysters (raw)", "grams": 84},
    {"term": ["mollusks, mussel"], "include": ["raw"], "exclude": ["cooked", "canned"],
     "label": "Mussels (raw)", "grams": 85},
    {"term": ["mollusks, clam"], "include": ["raw"], "exclude": ["cooked", "canned", "breaded"],
     "label": "Clams (raw)", "grams": 85},
    {"term": ["mollusks, scallop"], "include": ["raw"], "exclude": ["cooked", "breaded", "imitation"],
     "label": "Scallops (raw)", "grams": 85},
    {"term": ["soup, stock, fish", "fish stock"], "include": [], "exclude": [],
     "label": "Fish stock", "grams": 240},

    # --- ALLIUMS (leek already above under greens) ---
    {"term": ["garlic, raw"], "include": [], "exclude": ["powder", "cooked"],
     "label": "Garlic (raw)", "grams": 9},
    {"term": ["onions, raw"], "include": [], "exclude": ["cooked", "dehydrated", "powder", "rings", "spring", "young", "welsh"],
     "label": "Onions (raw)", "grams": 110},

    # --- FERMENTS & DAIRY FATS ---
    {"term": ["cheese, cheddar"], "include": ["sharp"], "exclude": ["low", "fat free", "nonfat", "spread", "reduced", "sliced"],
     "label": "Cheddar", "grams": 28},
    {"term": ["butter, without salt"], "include": [], "exclude": ["butterbur", "whipped", "light"],
     "label": "Butter (unsalted)", "grams": 14},
    {"term": ["clarified butter", "ghee"], "include": ["ghee"], "exclude": [],
     "label": "Ghee", "grams": 14},
    {"term": ["kefir"], "include": ["plain"], "exclude": ["strawberry", "vanilla", "flavored"],
     "label": "Kefir (plain)", "grams": 240},
    {"term": ["cheese, cottage"], "include": ["creamed", "large or small curd"], "exclude": ["low", "nonfat", "fat free", "with fruit"],
     "label": "Cottage cheese", "grams": 113},
    {"term": ["sauerkraut"], "include": ["canned", "solids and liquids"], "exclude": [],
     "label": "Sauerkraut", "grams": 100},

    # --- SWEETENER ---
    {"term": ["honey"], "include": [], "exclude": ["roasted", "mustard", "graham"],
     "label": "Honey", "grams": 21},
]

# Hard pins: when you KNOW the exact fdc_id you want, force it here.
# (label substring -> fdc_id). Overrides scoring.
PINS = {
    # "Hazelnuts": 170581,   # uncomment if the resolver still picks a regional entry
}


def score(desc, spec):
    d = desc.lower()
    if not any(t.lower() in d for t in spec["term"]):
        return None
    for ex in spec.get("exclude", []):
        if ex.lower() in d:
            return None
    s = 100 - len(d)
    for inc in spec.get("include", []):
        if inc.lower() in d:
            s += 50
    if any(d.startswith(t.lower()) for t in spec["term"]):
        s += 80
    return s


def resolve():
    foods = dl.load_foods()
    results, all_ids = [], set()
    for spec in STAPLE_SPECS:
        scored = []
        for fdc, desc in foods.items():
            sc = score(desc, spec)
            if sc is not None:
                scored.append((sc, fdc, desc))
        scored.sort(reverse=True)
        results.append((spec, scored[:4]))
        all_ids.update(fdc for _, fdc, _ in scored[:4])
    all_ids.update(PINS.values())
    fn = dl.load_food_nutrients(list(all_ids))

    repertoire, report = [], []
    for spec, cands in results:
        pin = PINS.get(spec["label"])
        if pin:
            desc = foods.get(pin, "")
            repertoire.append({"fdc_id": pin, "label": spec["label"],
                               "default_grams": spec["grams"],
                               "usda_description": desc, "tags": spec.get("tags", [])})
            p = fn.get(pin, {})
            report.append((spec["label"], pin,
                           [{"fdc": pin, "desc": desc, "kcal": round(p.get(1008, 0)),
                             "protein": round(p.get(1003, 0), 1), "chosen": True}]))
            continue
        if not cands:
            report.append((spec["label"], None, []))
            continue
        chosen = next((c for c in cands if c[1] in fn), cands[0])
        sc, fdc, desc = chosen
        repertoire.append({"fdc_id": fdc, "label": spec["label"],
                           "default_grams": spec["grams"],
                           "usda_description": desc, "tags": spec.get("tags", [])})
        snaps = []
        for _, cfdc, cdesc in cands:
            p = fn.get(cfdc, {})
            snaps.append({"fdc": cfdc, "desc": cdesc, "kcal": round(p.get(1008, 0)),
                          "protein": round(p.get(1003, 0), 1), "chosen": cfdc == fdc})
        report.append((spec["label"], fdc, snaps))
    return repertoire, report


def print_report(report):
    print("\n=== STAPLE RESOLUTION REPORT ===")
    print("Check each chosen line against its snapshot. Wrong match?")
    print("Edit that spec's include/exclude (or add a PIN) and re-run.\n")
    nomatch = []
    for label, fdc, snaps in report:
        if fdc is None:
            nomatch.append(label)
            print(f"  !! {label:30s} NO MATCH — adjust search term")
            continue
        for s in snaps:
            tick = "*" if s["chosen"] else " "
            mark = " <- chosen" if s["chosen"] else ""
            lab = label if s["chosen"] else ""
            print(f"  {tick} {lab:30s} {s['fdc']:>7}  {s['desc'][:44]:44s} "
                  f"{s['kcal']:>4} kcal {s['protein']:>5}g{mark}")
        print()
    if nomatch:
        print("NO-MATCH items:", ", ".join(nomatch))


if __name__ == "__main__":
    repertoire, report = resolve()
    print_report(report)
    if "--dry" not in sys.argv:
        path = os.path.join(os.path.dirname(__file__), "repertoire.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(repertoire, f, indent=2)
        print(f"\nWrote {len(repertoire)} staples to repertoire.json")
    else:
        print("\n(dry run — not written)")
