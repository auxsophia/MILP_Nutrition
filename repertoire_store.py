"""
repertoire_store.py
-------------------
Makes the repertoire editable and persistent. Instead of a hardcoded list,
your selected staples live in repertoire.json, which the picker page writes to.

If repertoire.json doesn't exist yet, it's seeded from the REPERTOIRE list in
repertoire.py (so existing setups keep working).

Each staple entry:
  { "fdc_id": int, "label": str, "default_grams": float,
    "usda_description": str, "tags": [str, ...] }

tags let you mark things like "branded-macros-only" or "weigh-dry" so the rest
of the tool can treat them appropriately.
"""
import json, os
import data_loader as dl

STORE = os.path.join(os.path.dirname(__file__), "repertoire.json")


def _seed_from_module():
    try:
        from repertoire import REPERTOIRE
        return [dict(item) for item in REPERTOIRE]
    except Exception:
        return []


def load():
    if os.path.exists(STORE):
        with open(STORE, encoding="utf-8") as f:
            return json.load(f)
    items = _seed_from_module()
    save(items)
    return items


def save(items):
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    return items


def add(fdc_id, label=None, default_grams=100, tags=None):
    items = load()
    fdc_id = int(fdc_id)
    if any(int(i["fdc_id"]) == fdc_id for i in items):
        # already present: update label/grams instead of duplicating
        for i in items:
            if int(i["fdc_id"]) == fdc_id:
                if label:
                    i["label"] = label
                i["default_grams"] = float(default_grams)
                if tags is not None:
                    i["tags"] = tags
        return save(items)
    foods = dl.load_foods()
    desc = foods.get(fdc_id, "")
    items.append({
        "fdc_id": fdc_id,
        "label": label or desc,
        "default_grams": float(default_grams),
        "usda_description": desc,
        "tags": tags or [],
    })
    return save(items)


def remove(fdc_id):
    items = [i for i in load() if int(i["fdc_id"]) != int(fdc_id)]
    return save(items)


def update_serving(fdc_id, grams):
    items = load()
    for i in items:
        if int(i["fdc_id"]) == int(fdc_id):
            i["default_grams"] = float(grams)
    return save(items)


def set_serving(fdc_id, qty, portion_desc, grams):
    """Persist a household-measure choice: qty x portion (e.g. 0.25 'cup').
    grams is the resolved gram weight, kept in default_grams so code that reads
    grams stays correct."""
    items = load()
    for i in items:
        if int(i["fdc_id"]) == int(fdc_id):
            i["serving"] = {"qty": float(qty), "portion_desc": portion_desc}
            i["default_grams"] = float(grams)
    return save(items)


def rename(fdc_id, new_label):
    """Change the display label for a food (e.g. 'Oysters (raw)' -> 'Oysters,
    canned'). Does not change what USDA entry it points to."""
    items = load()
    for i in items:
        if int(i["fdc_id"]) == int(fdc_id):
            i["label"] = new_label.strip() or i["label"]
    return save(items)


def set_preferred_portion(fdc_id, portion_desc, grams_each):
    """Set the food's DEFAULT unit to a household portion (e.g. '1 large egg',
    '1 cup'). Stores the portion as the serving with qty=1, so the planner shows
    whole portions instead of odd cup fractions. grams_each is grams per 1 unit."""
    items = load()
    for i in items:
        if int(i["fdc_id"]) == int(fdc_id):
            i["serving"] = {"qty": 1.0, "portion_desc": portion_desc}
            i["default_grams"] = float(grams_each)
            i["preferred_portion"] = portion_desc
    return save(items)


def search(term, limit=40):
    """
    Search loaded USDA food descriptions for a term. Returns matching foods
    with their fdc_id, description, and a quick nutrient snapshot (kcal,
    protein) so you can tell entries apart (e.g. 'in oil' vs 'in water').
    Prefers real food rows over sampling-provenance rows.
    """
    term = term.strip().lower()
    if not term:
        return []
    foods = dl.load_foods()
    matches = [(fdc, desc) for fdc, desc in foods.items()
               if term in desc.lower()]
    matches = matches[:limit]
    # pull a snapshot for the matched ids
    fn = dl.load_food_nutrients([fdc for fdc, _ in matches])
    out = []
    for fdc, desc in matches:
        prof = fn.get(fdc, {})
        out.append({
            "fdc_id": fdc,
            "description": desc,
            "kcal": round(prof.get(1008, 0)),     # energy
            "protein": round(prof.get(1003, 0), 1),
            "has_nutrients": fdc in fn,
        })
    # rank: entries that actually carry nutrient data first, then by description
    out.sort(key=lambda x: (not x["has_nutrients"], x["description"]))
    return out
