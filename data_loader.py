"""
data_loader.py
--------------
Reads USDA FoodData Central CSVs (Foundation Foods / SR Legacy schema) and
performs the core join:  food -> food_nutrient -> nutrient,  plus food_portion
for household serving sizes. Pure standard library, no pandas.

Every numeric cell is parsed with fail-soft helpers, because the real bulk CSVs
contain blank and malformed rows that would otherwise crash the load.
"""
import csv, os
from collections import defaultdict

DATA = os.path.join(os.path.dirname(__file__), "data")


def _read(name):
    path = os.path.join(DATA, name)
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _to_float(val):
    """Parse a CSV cell to float; None for blanks/garbage."""
    if val is None:
        return None
    val = val.strip()
    if val == "":
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _to_int(val):
    f = _to_float(val)
    return int(f) if f is not None else None


def load_nutrients():
    """nutrient_id -> {name, unit}"""
    out = {}
    for r in _read("nutrient.csv"):
        nid = _to_int(r.get("id"))
        if nid is None:
            continue
        out[nid] = {"name": r.get("name", ""), "unit": r.get("unit_name", "")}
    return out


def load_foods():
    """fdc_id -> description"""
    out = {}
    for r in _read("food.csv"):
        fdc = _to_int(r.get("fdc_id"))
        if fdc is None:
            continue
        out[fdc] = r.get("description", "")
    return out


def load_food_nutrients(fdc_ids=None):
    """fdc_id -> {nutrient_id: amount_per_100g}. Filters to fdc_ids if given."""
    keep = set(fdc_ids) if fdc_ids else None
    out = defaultdict(dict)
    for r in _read("food_nutrient.csv"):
        fdc = _to_int(r.get("fdc_id"))
        nid = _to_int(r.get("nutrient_id"))
        amt = _to_float(r.get("amount"))
        if fdc is None or nid is None or amt is None:
            continue
        if keep is not None and fdc not in keep:
            continue
        out[fdc][nid] = amt
    return out


def load_portions():
    """
    fdc_id -> list of {description, grams} where grams is grams PER ONE unit
    of that household measure (gram_weight / amount). Deduped by description.
    Skips malformed rows.
    """
    out = defaultdict(list)
    try:
        rows = _read("food_portion.csv")
    except FileNotFoundError:
        return out
    seen = defaultdict(set)
    for r in rows:
        fdc = _to_int(r.get("fdc_id"))
        gram_weight = _to_float(r.get("gram_weight"))
        amount = _to_float(r.get("amount")) or 1.0
        if fdc is None or gram_weight is None or amount == 0:
            continue
        desc = (r.get("modifier") or r.get("portion_description") or "portion").strip()
        if not desc or desc.lower() in ("quantity not specified", "portion"):
            desc = "serving"
        if desc in seen[fdc]:
            continue
        seen[fdc].add(desc)
        out[fdc].append({"description": desc, "grams": round(gram_weight / amount, 2)})
    return out


def food_snapshot(fdc_id):
    """Return a compact USDA snapshot for a food (for tooltips): description +
    key nutrients per 100g. Reads live from the data so it reflects exactly what
    the food points to."""
    foods = load_foods()
    fn = load_food_nutrients([fdc_id])
    nutrients = load_nutrients()
    per100 = fn.get(fdc_id, {})
    # key nutrients to show
    keys = [(1008, "kcal"), (1003, "protein g"), (1004, "fat g"), (1005, "carb g"),
            (1079, "fiber g"), (1090, "magnesium mg"), (1089, "iron mg"),
            (1087, "calcium mg"), (1093, "sodium mg")]
    snap = []
    for nid, lbl in keys:
        if nid in per100:
            snap.append({"label": lbl, "value": round(per100[nid], 1)})
    return {
        "fdc_id": fdc_id,
        "usda_description": foods.get(fdc_id, "(not found)"),
        "per_100g": snap,
    }


def _resolve_serving_grams(item, portions):
    """
    Given a repertoire item that may carry serving={qty, portion_desc}, compute
    the grams it represents. Falls back to default_grams.
    """
    serving = item.get("serving")
    if serving:
        qty = float(serving.get("qty", 1))
        pdesc = serving.get("portion_desc", "grams")
        if pdesc == "grams":
            return qty
        for p in portions:
            if p["description"] == pdesc:
                return round(qty * p["grams"], 2)
    return float(item.get("default_grams", 100))


def build_repertoire_table(repertoire):
    """
    repertoire: list of {fdc_id, label, default_grams, optional serving}
    Returns (rows, present_ids, missing, nutrients).
    Each row carries per_100g, per_serving (scaled to resolved serving grams),
    the portion options, and the resolved serving.
    """
    foods = load_foods()
    nutrients = load_nutrients()
    wanted = [item["fdc_id"] for item in repertoire]
    fn = load_food_nutrients(wanted)
    portions_all = load_portions()

    rows, present_ids, missing = [], [], []
    for item in repertoire:
        fdc = item["fdc_id"]
        if fdc not in foods or fdc not in fn:
            missing.append(item)
            continue
        present_ids.append(fdc)
        per100 = fn[fdc]
        portions = portions_all.get(fdc, [])
        grams = _resolve_serving_grams(item, portions)
        scaled = {nid: amt * grams / 100.0 for nid, amt in per100.items()}
        rows.append({
            "fdc_id": fdc,
            "label": item.get("label") or foods[fdc],
            "usda_description": foods[fdc],
            "default_grams": grams,
            "serving": item.get("serving"),
            "per_100g": per100,
            "per_serving": scaled,
            "portions": portions,
        })
    return rows, present_ids, missing, nutrients


def presence_report(repertoire):
    foods = load_foods()
    fn_ids = set(load_food_nutrients([i["fdc_id"] for i in repertoire]).keys())
    report = []
    for item in repertoire:
        fdc = item["fdc_id"]
        report.append({
            "label": item.get("label", str(fdc)),
            "fdc_id": fdc,
            "in_food_table": fdc in foods,
            "has_nutrients": fdc in fn_ids,
        })
    return report
