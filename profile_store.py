"""
profile_store.py
----------------
Persists the user profile to profile.json so every page reads the SAME profile.
Before this, the dashboard edited a browser-only copy while the optimizer read
the hardcoded DEFAULT_PROFILE — so changes on one page never reached the other.

Seeded from DEFAULT_PROFILE in repertoire.py on first use.
"""
import json, os

STORE = os.path.join(os.path.dirname(__file__), "profile.json")


def _seed():
    try:
        from repertoire import DEFAULT_PROFILE
        return dict(DEFAULT_PROFILE)
    except Exception:
        return {"sex": "male", "age": 38, "height_in": 71, "weight_lb": 200,
                "target_weight_lb": 170, "activity": "moderate", "goal": "lose",
                "protein_g_per_kg": 1.9}


def load():
    if os.path.exists(STORE):
        with open(STORE, encoding="utf-8") as f:
            return json.load(f)
    p = _seed()
    save(p)
    return p


def save(profile):
    # keep only known keys, coerce numerics where sensible
    clean = {}
    for k, v in profile.items():
        if v in (None, ""):
            continue
        clean[k] = v
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2)
    return clean


def update(partial):
    """Merge a partial profile and persist. An empty-string value CLEARS that
    key (e.g. clearing lean_mass_lb reverts BMR from Katch-McArdle to Mifflin)."""
    p = load()
    for k, v in partial.items():
        if v == "":
            p.pop(k, None)          # explicit clear
        elif v is not None:
            p[k] = v
    return save(p)
