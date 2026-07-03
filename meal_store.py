"""
meal_store.py
-------------
Persists named meals to meals.json, parallel to repertoire.json and profile.json.

A meal:
  {
    "id": "m_1699...",           # stable id
    "name": "Morning bowl",
    "items": [{"fdc_id": 169705, "servings": 1.0}, ...],
    "spices": "cinnamon, cardamom, sea salt",   # free text, not tracked
    "updated": "2026-06-27T..."
  }

Servings are in units of each food's default_grams (so servings * default_grams
= grams). The planner resolves grams and nutrients live from the repertoire.
"""
import json, os, time

STORE = os.path.join(os.path.dirname(__file__), "meals.json")


def load():
    if os.path.exists(STORE):
        with open(STORE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save(meals):
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(meals, f, indent=2)
    return meals


def _new_id():
    return "m_" + str(int(time.time() * 1000))


def upsert(meal):
    """Create or update a meal. If it has an id that exists, replace it; else add."""
    meals = load()
    meal = dict(meal)
    meal["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    if meal.get("id"):
        for i, m in enumerate(meals):
            if m["id"] == meal["id"]:
                meals[i] = meal
                save(meals)
                return meal
    meal["id"] = _new_id()
    meals.append(meal)
    save(meals)
    return meal


def delete(meal_id):
    meals = [m for m in load() if m.get("id") != meal_id]
    return save(meals)


def get(meal_id):
    for m in load():
        if m.get("id") == meal_id:
            return m
    return None
