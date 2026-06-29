"""
targets.py
----------
Turns a person's profile (height, weight, age, sex, activity, and optionally
DEXA lean-mass) into daily nutrient targets.

HONESTY NOTE — this is the crux of "recalculate all nutritional values":
Not everything scales with body size, and a tool that pretends otherwise is
lying with false precision. So targets are computed in three explicit classes:

  1. SCALES WITH BODY SIZE / COMPOSITION
     - Energy (calories): Mifflin-St Jeor from height/weight/age/sex x activity,
       OR Katch-McArdle from lean body mass when DEXA data is available
       (more accurate because it reflects body composition, not just mass).
     - Protein: grams per kg of *target* body weight (lean-mass-aware if DEXA).
     - Water: roughly with energy/body mass.

  2. SCALES WITH ENERGY INTAKE (a few B-vitamins are defined per 1000 kcal)
     - Thiamin, riboflavin, niacin have energy-referenced components.

  3. FIXED POPULATION RDA (does NOT scale with your weight)
     - Most vitamins and minerals: vitamin C, D, A, K, B6, B12, folate,
       calcium, iron, zinc, magnesium, etc. The RDA is a population value set
       by sex and age. Your being heavier or lighter does not change it.

The UI shows which class each target falls in, so "recalculate for my weight"
changes the things that genuinely depend on weight and leaves the rest fixed
with that fact made visible.

All RDA values below are adult reference intakes (US DRI). They are defaults;
a clinician would individualise. Sources: NIH ODS fact sheets / DRI tables.
"""

ACTIVITY = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

# Fixed adult RDAs by sex. (value, unit, nutrient_id used in the USDA join)
# nutrient_ids match nutrient.csv in the loader.
FIXED_RDA = {
    "male": {
        1087: ("Calcium", 1000, "MG"),
        1089: ("Iron", 8, "MG"),
        1090: ("Magnesium", 420, "MG"),
        1095: ("Zinc", 11, "MG"),
        1098: ("Copper", 0.9, "MG"),
        1103: ("Selenium", 55, "UG"),
        1106: ("Vitamin A", 900, "UG"),
        1162: ("Vitamin C", 90, "MG"),
        1109: ("Vitamin E", 15, "MG"),
        1114: ("Vitamin D", 15, "UG"),
        1185: ("Vitamin K", 120, "UG"),
        1175: ("Vitamin B6", 1.3, "MG"),
        1177: ("Folate", 400, "UG"),
        1178: ("Vitamin B12", 2.4, "UG"),
        1079: ("Fiber", 38, "G"),
        1092: ("Potassium", 3400, "MG"),
    },
    "female": {
        1087: ("Calcium", 1000, "MG"),
        1089: ("Iron", 18, "MG"),
        1090: ("Magnesium", 320, "MG"),
        1095: ("Zinc", 8, "MG"),
        1098: ("Copper", 0.9, "MG"),
        1103: ("Selenium", 55, "UG"),
        1106: ("Vitamin A", 700, "UG"),
        1162: ("Vitamin C", 75, "MG"),
        1109: ("Vitamin E", 15, "MG"),
        1114: ("Vitamin D", 15, "UG"),
        1185: ("Vitamin K", 90, "UG"),
        1175: ("Vitamin B6", 1.3, "MG"),
        1177: ("Folate", 400, "UG"),
        1178: ("Vitamin B12", 2.4, "UG"),
        1079: ("Fiber", 25, "G"),
        1092: ("Potassium", 2600, "MG"),
    },
}

# Tolerable Upper Intake Levels (UL) where relevant — for flagging excess.
UPPER_LIMITS = {
    1089: 45,    # iron mg
    1095: 40,    # zinc mg
    1162: 2000,  # vitamin C mg
    1114: 100,   # vitamin D ug
    1106: 3000,  # vitamin A ug (preformed)
    1090: 350,   # magnesium mg (from supplements only, flag softly)
    1093: 2300,  # sodium mg (CDL, not a UL but a ceiling)
}


def lbs_to_kg(lb): return lb * 0.453592
def in_to_cm(inch): return inch * 2.54


def bmr_mifflin(weight_kg, height_cm, age, sex):
    """Mifflin-St Jeor: the standard when body composition is unknown."""
    s = 5 if sex == "male" else -161
    return 10 * weight_kg + 6.25 * height_cm - 5 * age + s


def bmr_katch(lean_mass_kg):
    """Katch-McArdle: uses lean body mass (e.g. from DEXA). More accurate
    because two people of equal weight but different composition differ here."""
    return 370 + 21.6 * lean_mass_kg


def compute_targets(profile):
    """
    profile keys:
      sex: 'male'|'female'
      age: years
      height_in, weight_lb  (or height_cm, weight_kg)
      activity: key in ACTIVITY
      goal: 'lose'|'maintain'|'gain'  (applies a calorie delta)
      lean_mass_lb: optional (DEXA). If present, Katch-McArdle is used.
      target_weight_lb: optional, for protein scaling (defaults to weight)
      protein_g_per_kg: optional override (default 1.8 for active)
    Returns a dict with energy, macros, and the full micronutrient target set,
    each tagged with its scaling class.
    """
    sex = profile.get("sex", "male")
    age = float(profile.get("age", 35))
    weight_kg = profile.get("weight_kg") or lbs_to_kg(float(profile["weight_lb"]))
    height_cm = profile.get("height_cm") or in_to_cm(float(profile["height_in"]))
    activity = profile.get("activity", "moderate")
    goal = profile.get("goal", "maintain")
    lean_lb = profile.get("lean_mass_lb")
    target_lb = profile.get("target_weight_lb") or profile.get("weight_lb")
    target_kg = lbs_to_kg(float(target_lb)) if target_lb else weight_kg
    ppk = float(profile.get("protein_g_per_kg", 1.8))

    # --- Class 1: energy (scales with size/composition) ---
    if lean_lb:
        lean_kg = lbs_to_kg(float(lean_lb))
        bmr = bmr_katch(lean_kg)
        bmr_method = "Katch-McArdle (DEXA lean mass)"
    else:
        bmr = bmr_mifflin(weight_kg, height_cm, age, sex)
        bmr_method = "Mifflin-St Jeor"
    tdee = bmr * ACTIVITY.get(activity, 1.55)
    goal_delta = {"lose": -0.20, "maintain": 0.0, "gain": 0.10}.get(goal, 0.0)
    energy = tdee * (1 + goal_delta)

    # --- Class 1: protein (scales with target weight / lean mass) ---
    protein_g = round(target_kg * ppk)

    # macro frame: protein fixed by body, fat 25-35% energy, carb remainder
    fat_g = round(energy * 0.30 / 9)
    carb_g = round((energy - protein_g * 4 - fat_g * 9) / 4)

    targets = {
        "_meta": {
            "bmr": round(bmr), "bmr_method": bmr_method,
            "tdee": round(tdee), "energy": round(energy),
            "goal": goal, "weight_kg": round(weight_kg, 1),
            "target_kg": round(target_kg, 1), "protein_g_per_kg": ppk,
        },
        "energy": {
            "nutrient_id": 1008, "name": "Energy", "unit": "KCAL",
            "target": round(energy), "scaling": "body size/composition",
            "kind": "ceiling" if goal == "lose" else "target",
        },
        "protein": {
            "nutrient_id": 1003, "name": "Protein", "unit": "G",
            "target": protein_g, "scaling": "target body weight",
            "kind": "floor",
        },
        "fat": {
            "nutrient_id": 1004, "name": "Total fat", "unit": "G",
            "target": fat_g, "scaling": "% of energy", "kind": "band",
        },
        "carb": {
            "nutrient_id": 1005, "name": "Carbohydrate", "unit": "G",
            "target": carb_g, "scaling": "energy remainder", "kind": "band",
        },
    }

    # --- Class 3: fixed population RDAs (do NOT scale with weight) ---
    for nid, (name, val, unit) in FIXED_RDA[sex].items():
        targets[name.lower().replace(" ", "_")] = {
            "nutrient_id": nid, "name": name, "unit": unit,
            "target": val, "scaling": "fixed population RDA (sex/age)",
            "kind": "floor",
            "upper_limit": UPPER_LIMITS.get(nid),
        }

    return targets
