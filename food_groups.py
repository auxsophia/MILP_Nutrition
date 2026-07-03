"""
food_groups.py
--------------
Assigns each repertoire food a culinary GROUP (grains, legumes, greens, roots,
fruit, nuts, seeds, fish, shellfish, dairy, ferments, fats, alliums, sweetener)
the way you actually cook — not the USDA taxonomy, which splits things oddly
(sauerkraut under Vegetables, kefir under Dairy) and has no "ferments" concept.

Groups are inferred from the label + usda_description by keyword, so you don't
hand-label. The result is written back onto each repertoire entry as a "group"
field (same pattern as "tags"). Re-runnable; only fills missing//forced groups.

The GROUP_ORDER controls display order in the meal planner's ingredient picker.
"""

import re

GROUP_ORDER = ["grains", "legumes", "greens", "roots", "alliums", "fruit",
               "nuts", "seeds", "fish", "shellfish", "dairy", "ferments",
               "fats", "sweetener", "other"]

# keyword -> group. First match wins. Order matters: more specific / higher-
# priority groups first. Legumes BEFORE seeds (split peas are legumes, though
# their USDA description says "mature seeds"). Fruit rules use whole words to
# avoid "pea" matching "pear".
RULES = [
    ("ferments",  ["sauerkraut", "kefir", "kimchi", "yogurt", "miso", "tempeh", "kombucha"]),
    ("shellfish", ["oyster", "mussel", "clam", "scallop", "shrimp", "crab", "lobster", "mollusk"]),
    ("fish",      ["sardine", "herring", "mackerel", "salmon", "tuna", "anchovy", "cod", "trout", "fish"]),
    ("dairy",     ["cheese", "cheddar", "cottage", "milk", "cream", "egg", "kefir"]),
    ("fats",      ["butter", "ghee", "lard", "tallow"]),
    ("legumes",   ["split pea", "green pea", "peas", "bean", "lentil", "chickpea", "broadbean", "fava", "soy"]),
    ("nuts",      ["hazelnut", "walnut", "pecan", "almond", "cashew", "pistachio", "macadamia", "filbert"]),
    ("seeds",     ["chia", "hemp", "flax", "flaxseed", "pumpkin", "sunflower", "sesame", "squash seed"]),
    ("grains",    ["oats", "barley", "spelt", "wheat", "rye", "rice", "millet", "quinoa", "buckwheat", "grain", "cereal"]),
    ("alliums",   ["garlic", "onion", "leek", "shallot", "chive", "scallion"]),
    ("greens",    ["kale", "spinach", "cabbage", "broccoli", "sorrel", "dock", "chard", "lettuce", "collard", "arugula", "seaweed", "kelp"]),
    ("roots",     ["beet", "carrot", "parsnip", "turnip", "radish", "potato", "yam", "rutabaga"]),
    ("fruit",     ["apple", "pear", "raspberry", "raspberries", "blackberry", "blackberries",
                   "strawberry", "strawberries", "blueberry", "blueberries", "berry", "berries",
                   "cherry", "cherries", "pomegranate", "grape", "peach", "plum", "fig", "citrus", "orange", "melon"]),
    ("sweetener", ["honey", "syrup", "sugar", "molasses"]),
]


def _matches(text, keyword):
    """Whole-word (or phrase) match, so 'pea' doesn't match 'pear'."""
    return re.search(r"\b" + re.escape(keyword) + r"s?\b", text) is not None


def infer_group(label, usda_description=""):
    text = (label + " " + usda_description).lower()
    for group, keywords in RULES:
        if any(_matches(text, k) for k in keywords):
            return group
    return "other"


def annotate(repertoire, force=False):
    """Add a 'group' field to each repertoire item. If force, overwrite existing."""
    for item in repertoire:
        if force or not item.get("group"):
            item["group"] = infer_group(item.get("label", ""),
                                        item.get("usda_description", ""))
    return repertoire


def grouped(repertoire):
    """Return repertoire organized as {group: [items]} in GROUP_ORDER."""
    annotate(repertoire)
    out = {g: [] for g in GROUP_ORDER}
    for item in repertoire:
        g = item.get("group", "other")
        out.setdefault(g, []).append(item)
    # drop empty groups, preserve order
    return [(g, out[g]) for g in GROUP_ORDER if out.get(g)]
