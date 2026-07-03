"""
app.py
------
Flask dashboard + food-picker for the convergent-diet nutrition tool.

Pages:
  /          dashboard: profile, targets, repertoire coverage, presence
  /staples   food picker: search the real USDA data, add/remove staples

The repertoire is now persistent (repertoire_store.py -> repertoire.json),
so adds and removes from the picker survive restarts.

Run:
    python make_sample_data.py   # once, if you don't have real data yet
    python app.py                # http://127.0.0.1:5000
"""
import os
from flask import Flask, render_template, request, jsonify
import data_loader as dl
import targets as tg
import repertoire_store as store
import profile_store as pstore
import bioavailability as bio
import optimizer as opt
import meal_store as meals
import food_groups as fg
from repertoire import DEFAULT_PROFILE

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))


def coverage(servings, targets, rows, meal=None):
    by_id = {r["fdc_id"]: r for r in rows}
    totals = {}
    # rebuild rows scaled to the requested servings (per_serving may differ)
    scaled_rows = []
    for fdc, grams in servings.items():
        r = by_id.get(int(fdc))
        if not r:
            continue
        per_serv = {nid: per100 * grams / 100.0 for nid, per100 in r["per_100g"].items()}
        scaled_rows.append({**r, "per_serving": per_serv})
        for nid, amt in per_serv.items():
            totals[nid] = totals.get(nid, 0) + amt
    out = []
    for key, t in targets.items():
        if key == "_meta":
            continue
        nid = t["nutrient_id"]
        got = totals.get(nid, 0)
        tgt = t["target"]
        pct = round(100 * got / tgt) if tgt else 0
        out.append({
            "nid": nid, "name": t["name"], "unit": t["unit"], "got": round(got, 1),
            "target": tgt, "pct": pct, "kind": t["kind"], "scaling": t["scaling"],
            "upper_limit": t.get("upper_limit"),
            "over_upper": bool(t.get("upper_limit") and got > t["upper_limit"]),
        })
    # bioavailability-adjusted view for the handful of nutrients that warrant it
    adjusted, meal_used = bio.adjust_totals(totals, scaled_rows, meal)
    for row in out:
        a = adjusted.get(row["nid"])
        if a:
            row["absorbed"] = a["absorbed"]
            row["absorbed_low"] = a["low"]
            row["absorbed_high"] = a["high"]
            row["absorbed_pct"] = round(100 * a["absorbed"] / row["target"]) if row["target"] else 0
            row["absorbed_pct_low"] = round(100 * a["low"] / row["target"]) if row["target"] else 0
            row["absorbed_pct_high"] = round(100 * a["high"] / row["target"]) if row["target"] else 0
            row["basis"] = a["basis"]
    macro_names = {"Energy", "Protein", "Total fat", "Carbohydrate"}
    macros = [x for x in out if x["name"] in macro_names]
    micros = sorted([x for x in out if x["name"] not in macro_names],
                    key=lambda x: x.get("absorbed_pct", x["pct"]))
    return {"meta": targets["_meta"], "macros": macros, "micros": micros,
            "meal": meal_used}


@app.route("/")
def index():
    repertoire = store.load()
    profile = pstore.load()
    rows, present, missing, nutrients = dl.build_repertoire_table(repertoire)
    presence = dl.presence_report(repertoire)
    targets = tg.compute_targets(profile)
    default_servings = {r["fdc_id"]: r["default_grams"] for r in rows}
    cov = coverage(default_servings, targets, rows, bio.DEFAULT_MEAL)
    return render_template("index.html", profile=profile, rows=rows,
                           presence=presence, missing=missing, coverage=cov,
                           activities=list(tg.ACTIVITY.keys()))


@app.route("/staples")
def staples():
    repertoire = store.load()
    rows, present, missing, _ = dl.build_repertoire_table(repertoire)
    return render_template("staples.html", repertoire=repertoire,
                           rows=rows, missing=missing)


@app.route("/api/search")
def api_search():
    term = request.args.get("q", "")
    return jsonify(store.search(term))


@app.route("/api/staple/add", methods=["POST"])
def api_add():
    d = request.get_json(force=True)
    store.add(d["fdc_id"], d.get("label"), d.get("default_grams", 100), d.get("tags"))
    return jsonify({"ok": True, "repertoire": store.load()})


@app.route("/api/staple/remove", methods=["POST"])
def api_remove():
    d = request.get_json(force=True)
    store.remove(d["fdc_id"])
    return jsonify({"ok": True, "repertoire": store.load()})


@app.route("/api/staple/serving", methods=["POST"])
def api_serving():
    d = request.get_json(force=True)
    store.set_serving(d["fdc_id"], d["qty"], d["portion_desc"], d["grams"])
    return jsonify({"ok": True})


@app.route("/optimize")
def optimize_page():
    repertoire = store.load()
    profile = pstore.load()
    rows, *_ = dl.build_repertoire_table(repertoire)
    foods = [{"fdc_id": r["fdc_id"], "label": r["label"]} for r in rows]
    targets = tg.compute_targets(profile)
    return render_template("optimize.html", foods=foods, profile=profile,
                           meta=targets["_meta"], activities=list(tg.ACTIVITY.keys()))


@app.route("/api/optimize", methods=["POST"])
def api_optimize():
    d = request.get_json(force=True)
    # accept profile edits from the optimizer page and persist them
    if d.get("profile"):
        pstore.update(d["profile"])
    profile = pstore.load()
    mode = d.get("mode", "LP")
    method = d.get("method", "diet")        # diet | gapfind
    objective = d.get("objective", "min_calories")  # min_calories | hit_calories
    exclude = [int(x) for x in d.get("exclude", [])]
    current = {int(k): float(v) for k, v in d.get("current", {}).items()}
    repertoire = store.load()
    rows, *_ = dl.build_repertoire_table(repertoire)
    targets = tg.compute_targets(profile)

    if method == "gapfind":
        res = opt.gap_find(rows, targets, current, mode=mode, exclude=exclude)
    else:
        res = opt.solve_diet(rows, targets, mode=mode, objective=objective, exclude=exclude)

    if res["status"] != "Optimal":
        res["obstacles"] = opt.diagnose_infeasible(rows, targets, exclude=exclude)
        res["relaxed"] = opt.best_achievable(rows, targets, exclude=exclude)
    # echo the meta so the page can show what it solved against
    res["meta"] = targets["_meta"]
    return jsonify(res)


@app.route("/planner")
def planner_page():
    repertoire = store.load()
    rows, *_ = dl.build_repertoire_table(repertoire)
    row_by_id = {r["fdc_id"]: r for r in rows}
    rep_by_id = {i["fdc_id"]: i for i in repertoire}
    groups = []
    for gname, items in fg.grouped(repertoire):
        entries = []
        for it in items:
            r = row_by_id.get(it["fdc_id"])
            if not r:
                continue
            repitem = rep_by_id.get(it["fdc_id"], {})
            default_unit = _pick_default_unit(
                repitem.get("preferred_portion"), r["portions"],
                r["default_grams"], repitem.get("serving"))
            entries.append({
                "fdc_id": r["fdc_id"], "label": r["label"],
                "default_grams": r["default_grams"],
                "portions": r["portions"],
                "default_unit": default_unit,
            })
        if entries:
            groups.append({"group": gname, "foods": entries})
    saved = meals.load()
    return render_template("planner.html", groups=groups, saved=saved)


def _pick_default_unit(pref, portions, default_grams, serving):
    """Choose the unit a food is entered in by default. Prefers whole countable
    portions over cup fractions so '1 large egg' beats '0.53 cup'."""
    if pref:
        for p in portions:
            if p["description"] == pref:
                return {"desc": p["description"], "grams_each": p["grams"]}
    if serving and serving.get("portion_desc") and serving["portion_desc"] != "grams":
        for p in portions:
            if p["description"] == serving["portion_desc"]:
                return {"desc": p["description"], "grams_each": p["grams"]}
    countable = ["egg", "can", "slice", "fillet", "piece", "large", "medium",
                 "small", "fruit", "clove", "unit", "whole"]
    for p in portions:
        if any(w in p["description"].lower() for w in countable):
            return {"desc": p["description"], "grams_each": p["grams"]}
    for p in portions:
        if "cup" in p["description"].lower():
            return {"desc": p["description"], "grams_each": p["grams"]}
    return {"desc": "grams", "grams_each": 1.0}


def meal_nutrition(items, profile, meal_fraction=1.0):
    """Compute a meal's nutrition from [{fdc_id, servings}]. meal_fraction scales
    the daily targets (1.0 = full day, 0.4 = ~one of 2 meals + snack)."""
    repertoire = store.load()
    rows, *_ = dl.build_repertoire_table(repertoire)
    row_by_id = {r["fdc_id"]: r for r in rows}
    # build grams per food from servings
    servings = {}
    chosen_rows = []
    for it in items:
        r = row_by_id.get(int(it["fdc_id"]))
        if not r:
            continue
        grams = float(it["servings"]) * r["default_grams"]
        servings[r["fdc_id"]] = grams
        chosen_rows.append({**r, "grams": grams})
    targets = tg.compute_targets(profile)
    # scale targets by meal_fraction for the coverage display
    scaled = {}
    for k, t in targets.items():
        if k == "_meta":
            scaled[k] = t
            continue
        scaled[k] = {**t, "target": round(t["target"] * meal_fraction, 1)}
    cov = coverage(servings, scaled, rows, bio.DEFAULT_MEAL)
    # per-food contribution breakdown (reuse optimizer.contributions)
    a = {r["fdc_id"]: r["per_100g"] for r in rows}
    contribs = opt.contributions(
        [{"fdc_id": r["fdc_id"], "label": r["label"], "grams": r["grams"]} for r in chosen_rows],
        a, scaled)
    return {"coverage": cov, "contributions": contribs,
            "meal_fraction": meal_fraction}


@app.route("/api/meal/nutrition", methods=["POST"])
def api_meal_nutrition():
    d = request.get_json(force=True)
    profile = pstore.load()
    frac = float(d.get("meal_fraction", 1.0))
    return jsonify(meal_nutrition(d.get("items", []), profile, frac))


@app.route("/api/meal/save", methods=["POST"])
def api_meal_save():
    d = request.get_json(force=True)
    m = meals.upsert({
        "id": d.get("id"), "name": d.get("name", "Untitled meal"),
        "items": d.get("items", []), "spices": d.get("spices", ""),
    })
    return jsonify({"ok": True, "meal": m, "meals": meals.load()})


@app.route("/api/meal/delete", methods=["POST"])
def api_meal_delete():
    d = request.get_json(force=True)
    meals.delete(d["id"])
    return jsonify({"ok": True, "meals": meals.load()})


@app.route("/api/staple/rename", methods=["POST"])
def api_rename():
    d = request.get_json(force=True)
    store.rename(d["fdc_id"], d["label"])
    return jsonify({"ok": True, "repertoire": store.load()})


@app.route("/api/staple/preferred_portion", methods=["POST"])
def api_preferred_portion():
    d = request.get_json(force=True)
    store.set_preferred_portion(d["fdc_id"], d["portion_desc"], d["grams_each"])
    return jsonify({"ok": True, "repertoire": store.load()})


@app.route("/api/staple/snapshot")
def api_snapshot():
    fdc = int(request.args.get("fdc_id"))
    return jsonify(dl.food_snapshot(fdc))


@app.route("/api/recalculate", methods=["POST"])
def recalculate():
    payload = request.get_json(force=True)
    profile = payload.get("profile", pstore.load())
    pstore.save(profile)        # persist so the optimizer sees the same profile
    servings = {int(k): float(v) for k, v in payload.get("servings", {}).items()}
    meal = payload.get("meal")
    repertoire = store.load()
    rows, *_ = dl.build_repertoire_table(repertoire)
    targets = tg.compute_targets(profile)
    cov = coverage(servings, targets, rows, meal)
    return jsonify(cov)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
