"""
bioavailability.py
------------------
Adjusts CONTENT (what USDA reports is in the food) toward ABSORBED (what your
body actually takes up), for the handful of nutrients where the gap is large
AND the science is solid. Everything else passes through unchanged, because
adding coefficients where the effect is small would be inventing precision.

ADJUSTED (with published basis):
  - Iron   : heme vs non-heme absorption; vitamin C and meat enhance non-heme,
             phytate, calcium, tea/coffee inhibit it. (Monsen/Hallberg-style.)
  - Zinc   : phytate:zinc molar ratio drives fractional absorption. (IZiNCG.)
  - Vit A  : carotenoid provitamin A converts to retinol poorly; RAE already
             encodes the 12:1 (beta-carotene) / 24:1 factors, but whole-food
             matrix and fat presence modulate real uptake. Flagged, lightly adj.
  - Folate : food folate vs fortified folic acid differ; DFE convention applied.
  - Protein: digestibility/quality (DIAAS-style) discounts plant protein more
             than animal. Affects "usable protein," not the gram count.

NOT adjusted (content is a fair proxy): vitamin C, the B-vitamins broadly,
vitamin K, potassium, sodium, vitamin D, calcium (absorption fairly stable in
food amounts), magnesium (modest phytate effect, left as content with a note).

EVERY adjustment returns a POINT estimate AND a low/high band, because real
absorption varies several-fold with the individual and the meal. The tool shows
the band, never a single confident number.

Sources (for traceability, not reproduced here):
  Monsen et al. 1978; Hallberg & Hulthen 2000 (iron);
  IZiNCG 2004 / Miller et al. 2007 (zinc, phytate:zinc model);
  FAO/WHO 2001, IOM 2001 (carotenoid RAE, folate DFE);
  FAO 2013 (DIAAS protein quality).
"""

# nutrient ids (USDA)
IRON, ZINC, VIT_A, FOLATE, PROTEIN, VIT_C, CALCIUM, PHYTATE = \
    1089, 1095, 1106, 1177, 1003, 1162, 1087, 2999

# --- per-food bioavailability hints -----------------------------------------
# Where USDA doesn't carry phytate or heme fraction, we tag foods by class.
# class -> properties used by the models below.
FOOD_CLASS = {
    "animal_flesh": {"heme_fraction": 0.40, "phytate_mg_per_100g": 0,
                     "protein_quality": 1.0},   # fish, meat, shellfish
    "egg":          {"heme_fraction": 0.0, "phytate_mg_per_100g": 0,
                     "protein_quality": 1.0},
    "dairy":        {"heme_fraction": 0.0, "phytate_mg_per_100g": 0,
                     "protein_quality": 1.0},
    "legume":       {"heme_fraction": 0.0, "phytate_mg_per_100g": 600,
                     "protein_quality": 0.70},
    "grain":        {"heme_fraction": 0.0, "phytate_mg_per_100g": 400,
                     "protein_quality": 0.55},
    "nut_seed":     {"heme_fraction": 0.0, "phytate_mg_per_100g": 700,
                     "protein_quality": 0.65},
    "veg_fruit":    {"heme_fraction": 0.0, "phytate_mg_per_100g": 30,
                     "protein_quality": 0.65},
    "default":      {"heme_fraction": 0.0, "phytate_mg_per_100g": 100,
                     "protein_quality": 0.75},
}


def classify(usda_description):
    d = (usda_description or "").lower()
    if any(k in d for k in ["fish", "mollusk", "oyster", "mussel", "clam",
                            "scallop", "beef", "pork", "lamb", "chicken",
                            "liver", "meat", "sardine", "herring", "mackerel"]):
        return "animal_flesh"
    if "egg" in d:
        return "egg"
    if any(k in d for k in ["cheese", "kefir", "milk", "butter", "yogurt",
                            "cottage", "ghee", "cream"]):
        return "dairy"
    if any(k in d for k in ["pea", "bean", "lentil", "broadbean", "fava", "chickpea"]):
        return "legume"
    if any(k in d for k in ["oats", "barley", "spelt", "wheat", "rye", "rice",
                            "grain", "cereal"]):
        return "grain"
    if any(k in d for k in ["nut", "seed", "hazelnut", "walnut", "pecan",
                            "almond", "chia", "flax", "hemp"]):
        return "nut_seed"
    if any(k in d for k in ["kale", "spinach", "cabbage", "broccoli", "beet",
                            "carrot", "parsnip", "leek", "onion", "garlic",
                            "sorrel", "dock", "berry", "berries", "apple",
                            "pear", "cherr", "pomegranate", "seaweed", "kelp",
                            "sauerkraut", "fruit", "vegetable"]):
        return "veg_fruit"
    return "default"


# --- the models -------------------------------------------------------------

def iron_absorbed(content_mg, food_class, meal):
    """
    Split into heme and non-heme, apply fractional absorption, modulate non-heme
    by meal enhancers/inhibitors. Returns (point, low, high) mg absorbed.
    """
    props = FOOD_CLASS[food_class]
    heme = content_mg * props["heme_fraction"]
    nonheme = content_mg - heme
    # baseline absorption fractions (iron-replete reference person)
    heme_abs = 0.25
    nonheme_abs = 0.05
    # meal modulation on non-heme only
    if meal.get("vitamin_c"):
        nonheme_abs *= 2.5          # ascorbate strongly enhances
    if meal.get("meat_factor"):
        nonheme_abs *= 1.5          # MFP factor
    if meal.get("tea_coffee"):
        nonheme_abs *= 0.5          # polyphenols inhibit
    if meal.get("high_calcium"):
        nonheme_abs *= 0.7
    if food_class in ("legume", "grain", "nut_seed") and not meal.get("soaked_fermented"):
        nonheme_abs *= 0.6          # phytate drag if not soaked/fermented
    nonheme_abs = min(nonheme_abs, 0.40)
    point = heme * heme_abs + nonheme * nonheme_abs
    # several-fold individual variation -> wide band
    return point, point * 0.6, point * 1.8


def zinc_absorbed(content_mg, food_class, meal):
    """
    Phytate:zinc molar ratio model (simplified IZiNCG). Higher ratio -> lower
    fractional absorption. Returns (point, low, high) mg absorbed.
    """
    props = FOOD_CLASS[food_class]
    phy = props["phytate_mg_per_100g"]
    if meal.get("soaked_fermented") and food_class in ("legume", "grain", "nut_seed"):
        phy *= 0.5
    # molar ratio: phytate MW 660, zinc MW 65.4; per 100g basis is fine for ratio
    if content_mg <= 0:
        return 0.0, 0.0, 0.0
    molar_ratio = (phy / 660.0) / max(content_mg / 65.4, 1e-6)
    # fractional absorption declines with ratio (IZiNCG-style brackets)
    if molar_ratio < 5:
        frac = 0.34
    elif molar_ratio < 15:
        frac = 0.26
    elif molar_ratio < 30:
        frac = 0.18
    else:
        frac = 0.12
    point = content_mg * frac
    return point, point * 0.7, point * 1.4


def vitamin_a_adjusted(content_ug_rae, food_class, meal):
    """
    USDA RAE already encodes the poor carotenoid conversion (12:1 / 24:1). The
    remaining real-world modulation is fat presence (carotenoids need fat to
    absorb) for plant sources. Animal/dairy retinol is well absorbed. Returns
    (point, low, high) ug RAE effective.
    """
    if food_class in ("animal_flesh", "egg", "dairy"):
        return content_ug_rae, content_ug_rae * 0.85, content_ug_rae * 1.0
    # plant carotenoid source
    frac = 0.9 if meal.get("fat_present") else 0.5
    point = content_ug_rae * frac
    return point, point * 0.6, point * 1.2


def folate_adjusted(content_ug, meal):
    """
    Food folate is ~50% as bioavailable as folic acid; USDA 'Folate, total' is
    food folate, so we present it as DFE-equivalent with a band. Light touch.
    """
    point = content_ug * 0.85   # cooking losses + matrix
    return point, content_ug * 0.6, content_ug * 1.0


def protein_usable(content_g, food_class):
    """
    Discount by digestibility/quality (DIAAS-style). The gram count is real;
    'usable' protein for tissue is lower for plant sources. Returns (point, lo, hi).
    """
    q = FOOD_CLASS[food_class]["protein_quality"]
    point = content_g * q
    return point, point * 0.9, point * 1.05


# --- meal context -----------------------------------------------------------
DEFAULT_MEAL = {
    "vitamin_c": False,       # vitamin-C-rich food in the same meal?
    "meat_factor": False,     # meat/fish/poultry in the same meal?
    "tea_coffee": False,      # tea or coffee with the meal?
    "high_calcium": False,    # large dairy/calcium load in the same meal?
    "soaked_fermented": True, # legumes/grains soaked, sprouted, or fermented?
    "fat_present": True,      # fat in the meal (for carotenoid uptake)?
}


def adjust_totals(content_totals, rows, meal=None):
    """
    content_totals: {nutrient_id: summed content across the plate}
    rows: the repertoire rows (to know each food's class and contribution)
    Returns a dict of adjusted nutrients, each with content, absorbed point,
    low, high, and a short basis string. Only the adjusted nutrients appear;
    callers merge these over the content view.

    Because absorption is per-food (a food's iron heme fraction differs), we
    recompute per food and sum, rather than adjusting the pooled total.
    """
    meal = {**DEFAULT_MEAL, **(meal or {})}
    # accumulate absorbed per nutrient across foods
    acc = {IRON: [0, 0, 0], ZINC: [0, 0, 0], VIT_A: [0, 0, 0],
           FOLATE: [0, 0, 0], PROTEIN: [0, 0, 0]}
    for r in rows:
        cls = classify(r.get("usda_description", ""))
        serv = r["per_serving"]
        def add(nid, triple):
            acc[nid][0] += triple[0]; acc[nid][1] += triple[1]; acc[nid][2] += triple[2]
        if IRON in serv:
            add(IRON, iron_absorbed(serv[IRON], cls, meal))
        if ZINC in serv:
            add(ZINC, zinc_absorbed(serv[ZINC], cls, meal))
        if VIT_A in serv:
            add(VIT_A, vitamin_a_adjusted(serv[VIT_A], cls, meal))
        if FOLATE in serv:
            add(FOLATE, folate_adjusted(serv[FOLATE], meal))
        if PROTEIN in serv:
            add(PROTEIN, protein_usable(serv[PROTEIN], cls))

    basis = {
        IRON: "heme/non-heme split; meal enhancers & inhibitors applied",
        ZINC: "phytate:zinc molar-ratio model",
        VIT_A: "carotenoid conversion (RAE) + fat-dependent uptake",
        FOLATE: "food-folate bioavailability + cooking loss",
        PROTEIN: "digestibility/quality discount (DIAAS-style)",
    }
    out = {}
    for nid, (pt, lo, hi) in acc.items():
        out[nid] = {
            "content": round(content_totals.get(nid, 0), 1),
            "absorbed": round(pt, 2),
            "low": round(lo, 2),
            "high": round(hi, 2),
            "basis": basis[nid],
        }
    return out, meal
