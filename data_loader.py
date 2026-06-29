"""
data_loader.py
--------------
Reads USDA FoodData Central CSVs (Foundation Foods schema) and performs the
core join:  food -> food_nutrient -> nutrient,  plus food_portion for serving
sizes. Pure standard library (csv), no pandas dependency, so it runs anywhere.

The same code reads the sample data and the real download, because they share
the schema. If your real download is large, this loads in a second or two
because we filter to the repertoire early.
"""
import csv, os
from collections import defaultdict

DATA = os.path.join(os.path.dirname(__file__), "data")


def _read(name):
    path = os.path.join(DATA, name)
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_nutrients():
    """nutrient_id -> {name, unit}"""
    out = {}
    for r in _read("nutrient.csv"):
        out[int(float(r["id"]))] = {"name": r["name"], "unit": r["unit_name"]}
    return out


def load_foods():
    """fdc_id -> description"""
    out = {}
    for r in _read("food.csv"):
        out[int(float(r["fdc_id"]))] = r["description"]
    return out


def load_food_nutrients(fdc_ids=None):
    """fdc_id -> {nutrient_id: amount_per_100g}. Filters to fdc_ids if given."""
    keep = set(fdc_ids) if fdc_ids else None
    out = defaultdict(dict)
    for r in _read("food_nutrient.csv"):
        fdc = int(float(r["fdc_id"]))
        if keep is not None and fdc not in keep:
            continue
        try:
            out[fdc][int(float(r["nutrient_id"]))] = float(r["amount"])
        except (ValueError, KeyError):
            continue
    return out


def load_portions():
    """fdc_id -> list of {description, grams}"""
    out = defaultdict(list)
    try:
        rows = _read("food_portion.csv")
    except FileNotFoundError:
        return out
    for r in rows:
        fdc = int(float(r["fdc_id"]))
        desc = (r.get("modifier") or r.get("portion_description") or "portion").strip()
        try:
            grams = float(r["gram_weight"])
        except (ValueError, KeyError):
            continue
        out[fdc].append({"description": desc, "grams": grams})
    return out


def build_repertoire_table(repertoire):
    """
    repertoire: list of {fdc_id, label, default_grams}
    Returns (rows, present_ids, missing) where each row carries the food's
    nutrient profile scaled to its default serving, plus per-100g for the solver.
    """
    foods = load_foods()
    nutrients = load_nutrients()
    wanted = [item["fdc_id"] for item in repertoire]
    fn = load_food_nutrients(wanted)
    portions = load_portions()

    rows, present_ids, missing = [], [], []
    for item in repertoire:
        fdc = item["fdc_id"]
        if fdc not in foods or fdc not in fn:
            missing.append(item)
            continue
        present_ids.append(fdc)
        per100 = fn[fdc]
        grams = item.get("default_grams", 100)
        scaled = {nid: amt * grams / 100.0 for nid, amt in per100.items()}
        rows.append({
            "fdc_id": fdc,
            "label": item.get("label") or foods[fdc],
            "usda_description": foods[fdc],
            "default_grams": grams,
            "per_100g": per100,
            "per_serving": scaled,
            "portions": portions.get(fdc, []),
        })
    return rows, present_ids, missing, nutrients


def presence_report(repertoire):
    """Quick check: which repertoire items are in the loaded dataset?"""
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
