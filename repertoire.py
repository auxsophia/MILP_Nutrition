"""
repertoire.py
-------------
Seed staple list + default profile. Once repertoire.json exists (created by the
picker on first use), THAT file is the live repertoire and this list is only the
initial seed. Edit staples on the /staples page rather than here.

The fdc_ids below are REAL SR Legacy ids. Swap in SR Legacy data (data/) and they
resolve directly. A few notes on the tricky ones are inline.
"""

REPERTOIRE = [
    # grains — use UNCOOKED entries and weigh dry (tag: weigh-dry)
    {"fdc_id": 169745, "label": "Spelt (dry)",   "default_grams": 80, "tags": ["weigh-dry"]},   # Spelt, uncooked
    {"fdc_id": 168871, "label": "Oats (dry)",    "default_grams": 80, "tags": ["weigh-dry"]},   # Oats  (verify id in your data)
    {"fdc_id": 170284, "label": "Barley (dry)",  "default_grams": 80, "tags": ["weigh-dry"]},   # Barley, hulled (verify)
    {"fdc_id": 172421, "label": "Split peas (dry)","default_grams": 100,"tags": ["weigh-dry"]}, # Peas, split, mature seeds, raw (verify)

    # fish & eggs
    {"fdc_id": 175139, "label": "Sardines (oil, drained, w/ bone)", "default_grams": 92},
    {"fdc_id": 173672, "label": "Mackerel (Pacific, raw)",          "default_grams": 112},
    {"fdc_id": 171706, "label": "Herring (Atlantic, raw)",          "default_grams": 100},        # verify id
    {"fdc_id": 171287, "label": "Egg, whole, raw",                  "default_grams": 100},        # verify id

    # dairy & fats
    {"fdc_id": 170904, "label": "Kefir (lowfat, plain)",            "default_grams": 240},        # SR Legacy only has lowfat
    {"fdc_id": 173430, "label": "Butter, unsalted",                "default_grams": 14},          # verify id
    {"fdc_id": 171314, "label": "Ghee (clarified butter)",         "default_grams": 14},
    {"fdc_id": 171247, "label": "Cheddar, aged",                   "default_grams": 28},          # verify id

    # vegetables, ferment, nuts, fruit
    {"fdc_id": 168421, "label": "Kale, raw",                       "default_grams": 67},
    {"fdc_id": 169279, "label": "Sauerkraut",                      "default_grams": 100},          # verify id
    {"fdc_id": 170581, "label": "Hazelnuts",                       "default_grams": 28},           # verify id
    {"fdc_id": 171287, "label": "Chia seeds (dry)",               "default_grams": 24, "tags": ["weigh-dry"]},  # verify id
    {"fdc_id": 171711, "label": "Blueberries, raw",              "default_grams": 100},           # verify id
]

DEFAULT_PROFILE = {
    "sex": "male",
    "age": 38,
    "height_in": 68,
    "weight_lb": 200,
    "target_weight_lb": 170,
    "activity": "moderate",
    "goal": "lose",
    "protein_g_per_kg": 1.9,
    # "lean_mass_lb": 150,   # uncomment when you have a DEXA scan
}
