"""
optimizer.py
------------
The constraint-optimization core. Three modes, all built on the same
food -> nutrient matrix:

  1. solve_diet(...)   the classic Stigler-style problem: pick foods (and how
     much) to meet every nutrient floor under a calorie ceiling, minimizing an
     objective. LP = continuous grams; MILP = whole servings.

  2. gap_find(...)     given what you're ALREADY eating, find the smallest
     addition from the repertoire that closes the remaining floors. This is the
     honest, useful mode — it can't return an inedible answer because YOU chose
     the base.

  3. feasible(...)     can the repertoire meet all floors under the cap at all?
     Infeasibility is real information (supplementation is structurally required).

Honesty notes baked in:
  - Per-food upper bounds prevent degenerate "eat 2kg of one food" answers.
  - You can EXCLUDE foods (the "no, not sardines-and-oatmeal" lever).
  - The optimizer works on CONTENT, not absorbed values, because absorption is
    meal-dependent and would make the program circular/non-linear. The dashboard's
    absorbed view is the reality check on whatever the optimizer proposes.
  - The Stigler trap is expected: minimizing calories subject to floors yields
    monotonous answers. That's a feature to SEE, not a bug to hide.
"""
import pulp

# nutrient ids
ENERGY, PROTEIN, FAT, CARB, SODIUM = 1008, 1003, 1004, 1005, 1093


def _matrix(rows):
    """Return per-100g nutrient lookup, per-food serving grams, label, portions."""
    a = {}            # fdc_id -> {nutrient_id: per_100g}
    serving = {}      # fdc_id -> grams in one 'serving' (default_grams)
    label = {}
    portions = {}     # fdc_id -> list of {description, grams}
    for r in rows:
        a[r["fdc_id"]] = r["per_100g"]
        serving[r["fdc_id"]] = r.get("default_grams", 100) or 100
        label[r["fdc_id"]] = r["label"]
        portions[r["fdc_id"]] = r.get("portions", [])
    return a, serving, label, portions


def _household(grams, portions):
    """Render grams as a human measure, e.g. '2 large eggs', '0.25 cup'.
    Picks the most sensible portion: prefer count-like (egg/can/slice) then cup,
    then any. Returns a short string or '' if no portion data."""
    if not portions or grams <= 0:
        return ""
    # rank portions: countable units first, then cup, then others
    def rank(p):
        d = p["description"].lower()
        if any(w in d for w in ["egg", "can", "slice", "fillet", "piece", "large", "medium", "small", "fruit", "clove"]):
            return 0
        if "cup" in d:
            return 1
        if any(w in d for w in ["tbsp", "tablespoon", "tsp", "teaspoon", "oz"]):
            return 2
        return 3
    best = sorted(portions, key=rank)[0]
    if best["grams"] <= 0:
        return ""
    qty = grams / best["grams"]
    # round to a friendly fraction
    if qty >= 1:
        q = round(qty * 4) / 4          # nearest quarter
        q = int(q) if q == int(q) else q
    else:
        q = round(qty * 4) / 4 or round(qty, 2)
    desc = best["description"]
    return f"{q} {desc}"


def _floors_ceilings(targets):
    floors, ceilings = {}, {}
    for key, t in targets.items():
        if key == "_meta":
            continue
        nid = t["nutrient_id"]
        if t["kind"] == "floor":
            floors[nid] = t["target"]
        if nid == ENERGY:
            ceilings[ENERGY] = t["target"]      # energy as ceiling
        if t.get("upper_limit"):
            ceilings[nid] = t["upper_limit"]
    return floors, ceilings


def solve_diet(rows, targets, mode="LP", objective="min_calories",
               exclude=None, max_grams=400, max_servings=6):
    """
    Pick foods/amounts to meet all floors under the energy ceiling.
    mode: 'LP' (grams, continuous) or 'MILP' (integer servings).
    Returns a result dict.
    """
    exclude = set(exclude or [])
    a, serving, label, portions = _matrix(rows)
    floors, ceilings = _floors_ceilings(targets)
    ids = [f for f in a if f not in exclude]

    prob = pulp.LpProblem("diet", pulp.LpMinimize)

    if mode == "MILP":
        # integer servings; grams = servings * serving_grams
        x = {f: pulp.LpVariable(f"x_{f}", lowBound=0, upBound=max_servings, cat="Integer") for f in ids}
        grams = {f: x[f] * serving[f] for f in ids}
    else:
        # continuous grams
        x = {f: pulp.LpVariable(f"x_{f}", lowBound=0, upBound=max_grams) for f in ids}
        grams = {f: x[f] for f in ids}

    def amount(nid):
        return pulp.lpSum(a[f].get(nid, 0) * grams[f] / 100.0 for f in ids)

    energy_target = ceilings.get(ENERGY)

    # objective
    if objective == "hit_calories" and energy_target:
        # land ON the calorie target (not just under it): minimize |kcal - target|.
        # Modeled with two non-negative deviation vars; the ENERGY ceiling below
        # is relaxed to allow reaching the target exactly.
        over = pulp.LpVariable("kcal_over", lowBound=0)
        under = pulp.LpVariable("kcal_under", lowBound=0)
        prob += over + under
        prob += amount(ENERGY) - energy_target == over - under
    elif objective == "min_mass":
        prob += pulp.lpSum(grams[f] for f in ids)
    else:  # min_calories (default)
        prob += amount(ENERGY)

    # floors
    for nid, tgt in floors.items():
        prob += amount(nid) >= tgt
    # ceilings — for hit_calories, the energy ceiling is the target itself (we
    # allow landing exactly on it); other ceilings (ULs, sodium) still apply.
    for nid, cap in ceilings.items():
        if nid == ENERGY and objective == "hit_calories":
            continue
        prob += amount(nid) <= cap

    status = prob.solve(pulp.PULP_CBC_CMD(msg=0))
    return _package(prob, status, ids, x, grams, serving, label, a, targets, mode, portions)


def gap_find(rows, targets, current, mode="LP", exclude=None,
             max_grams=300, max_servings=4):
    """
    current: {fdc_id: grams} you're already eating.
    Find the minimal-calorie ADDITION (from foods not excluded) to meet floors.
    Foods already in `current` contribute as constants.
    """
    exclude = set(exclude or [])
    a, serving, label, portions = _matrix(rows)
    floors, ceilings = _floors_ceilings(targets)
    addable = [f for f in a if f not in exclude]

    # base contribution from current intake
    base = {}
    for nid in set().union(*[set(a[f]) for f in a]) if a else set():
        base[nid] = sum(a[f].get(nid, 0) * g / 100.0 for f, g in current.items() if f in a)

    prob = pulp.LpProblem("gapfind", pulp.LpMinimize)
    if mode == "MILP":
        x = {f: pulp.LpVariable(f"x_{f}", lowBound=0, upBound=max_servings, cat="Integer") for f in addable}
        grams = {f: x[f] * serving[f] for f in addable}
    else:
        x = {f: pulp.LpVariable(f"x_{f}", lowBound=0, upBound=max_grams) for f in addable}
        grams = {f: x[f] for f in addable}

    def added(nid):
        return pulp.lpSum(a[f].get(nid, 0) * grams[f] / 100.0 for f in addable)

    prob += added(ENERGY)   # minimize added calories
    for nid, tgt in floors.items():
        prob += base.get(nid, 0) + added(nid) >= tgt
    for nid, cap in ceilings.items():
        prob += base.get(nid, 0) + added(nid) <= cap

    status = prob.solve(pulp.PULP_CBC_CMD(msg=0))
    res = _package(prob, status, addable, x, grams, serving, label, a, targets, mode, portions)
    res["base"] = current
    return res


def feasible(rows, targets, exclude=None):
    """Just ask: is there ANY way to meet all floors under the cap?"""
    r = solve_diet(rows, targets, mode="LP", objective="min_calories", exclude=exclude)
    return r["status"] == "Optimal", r


def diagnose_infeasible(rows, targets, exclude=None):
    """
    When the diet is infeasible, find which floors are the obstacle. Solves a
    relaxed problem that maximizes how many floors can be met, and reports the
    floors that have to be dropped (the structural gaps requiring other foods or
    supplements). Returns a list of {name, target, best_achievable}.
    """
    exclude = set(exclude or [])
    a, serving, label, portions = _matrix(rows)
    floors, ceilings = _floors_ceilings(targets)
    ids = [f for f in a if f not in exclude]
    name = {t["nutrient_id"]: t["name"] for k, t in targets.items() if k != "_meta"}

    obstacles = []
    for nid, tgt in floors.items():
        prob = pulp.LpProblem("maxnut", pulp.LpMaximize)
        x = {f: pulp.LpVariable(f"x_{f}", lowBound=0, upBound=400) for f in ids}
        prob += pulp.lpSum(a[f].get(nid, 0) * x[f] / 100.0 for f in ids)
        if ENERGY in ceilings:
            prob += pulp.lpSum(a[f].get(ENERGY, 0) * x[f] / 100.0 for f in ids) <= ceilings[ENERGY]
        prob.solve(pulp.PULP_CBC_CMD(msg=0))
        best = pulp.value(prob.objective) or 0
        if best < tgt * 0.999:
            obstacles.append({"name": name.get(nid, str(nid)),
                              "target": round(tgt, 1), "best": round(best, 1),
                              "pct": round(100 * best / tgt)})
    obstacles.sort(key=lambda o: o["pct"])
    return obstacles


def best_achievable(rows, targets, exclude=None, max_grams=400):
    """
    The graceful failure. Instead of returning 'infeasible', solve a RELAXED
    problem that permits shortfalls on each floor, minimizing total proportional
    shortfall under the calorie ceiling. Always returns a real diet plus a
    per-nutrient readout of exactly where (and how far) it falls short.

    Also computes the minimum calorie ceiling that WOULD make the diet feasible,
    so the user sees whether their deficit is simply too aggressive for full
    micronutrient coverage from food alone.
    """
    exclude = set(exclude or [])
    a, serving, label, portions = _matrix(rows)
    floors, ceilings = _floors_ceilings(targets)
    ids = [f for f in a if f not in exclude]
    name = {t["nutrient_id"]: t["name"] for k, t in targets.items() if k != "_meta"}
    energy_cap = ceilings.get(ENERGY)

    # --- relaxed solve: minimize summed proportional shortfall ---
    prob = pulp.LpProblem("relaxed", pulp.LpMinimize)
    x = {f: pulp.LpVariable(f"x_{f}", lowBound=0, upBound=max_grams) for f in ids}
    short = {nid: pulp.LpVariable(f"s_{nid}", lowBound=0) for nid in floors}

    def amount(nid):
        return pulp.lpSum(a[f].get(nid, 0) * x[f] / 100.0 for f in ids)

    # objective: total proportional shortfall (each nutrient weighted equally).
    # Note: this minimizes how far floors are missed; it does NOT try to fill the
    # calorie budget, so the best-achievable plate can sit under the cap once the
    # floors are as-met-as-possible. That's intended — it's the leanest plate that
    # gets closest to complete, not a maintenance menu.
    prob += pulp.lpSum(short[nid] / max(tgt, 1e-6) for nid, tgt in floors.items())
    for nid, tgt in floors.items():
        prob += amount(nid) + short[nid] >= tgt        # may fall short by short[nid]
    for nid, cap in ceilings.items():
        prob += amount(nid) <= cap                      # ceilings still hard
    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    chosen = []
    for f in ids:
        v = x[f].value() or 0
        if v > 1e-3:
            chosen.append({"fdc_id": f, "label": label[f], "grams": round(v, 1),
                           "household": _household(v, portions.get(f, []))})
    chosen.sort(key=lambda c: -c["grams"])

    totals = {}
    for c in chosen:
        for nid, per100 in a[c["fdc_id"]].items():
            totals[nid] = totals.get(nid, 0) + per100 * c["grams"] / 100.0

    shortfalls = []
    for nid, tgt in floors.items():
        got = totals.get(nid, 0)
        pct = round(100 * got / tgt) if tgt else 100
        if pct < 99:
            shortfalls.append({"name": name.get(nid, str(nid)), "target": round(tgt, 1),
                               "got": round(got, 1), "pct": pct})
    shortfalls.sort(key=lambda s: s["pct"])

    # --- minimum calorie ceiling that makes it fully feasible ---
    min_kcal = None
    if energy_cap and shortfalls:
        prob2 = pulp.LpProblem("minkcal", pulp.LpMinimize)
        x2 = {f: pulp.LpVariable(f"y_{f}", lowBound=0, upBound=max_grams) for f in ids}
        prob2 += pulp.lpSum(a[f].get(ENERGY, 0) * x2[f] / 100.0 for f in ids)
        for nid, tgt in floors.items():
            prob2 += pulp.lpSum(a[f].get(nid, 0) * x2[f] / 100.0 for f in ids) >= tgt
        # keep non-energy ceilings (ULs, sodium)
        for nid, cap in ceilings.items():
            if nid != ENERGY:
                prob2 += pulp.lpSum(a[f].get(nid, 0) * x2[f] / 100.0 for f in ids) <= cap
        st2 = prob2.solve(pulp.PULP_CBC_CMD(msg=0))
        if pulp.LpStatus[st2] == "Optimal":
            min_kcal = round(pulp.value(prob2.objective))

    return {
        "status": "Relaxed",
        "foods": chosen,
        "energy": round(totals.get(ENERGY, 0)),
        "energy_cap": round(energy_cap) if energy_cap else None,
        "shortfalls": shortfalls,
        "min_feasible_kcal": min_kcal,
        "n_foods": len(chosen),
        "contributions": contributions(chosen, a, targets),
    }


def contributions(chosen_foods, a, targets, key_nutrients=None):
    """
    Per-nutrient breakdown: for each tracked nutrient, how much each food
    contributes (for the stacked contribution bars). Returns a list of:
      {nutrient, unit, target, total, pct, segments:[{label, amount, pct_of_target}]}
    key_nutrients: list of nutrient_ids to include (defaults to a useful subset
    plus any floor that's currently short).
    """
    tmeta = {t["nutrient_id"]: t for k, t in targets.items() if k != "_meta"}
    if key_nutrients is None:
        # headline + common-gap nutrients
        key_nutrients = [PROTEIN, 1090, 1089, 1095, 1087, 1092, 1079, 1162]  # protein, Mg, Fe, Zn, Ca, K, fiber, vit C
        key_nutrients = [n for n in key_nutrients if n in tmeta]
    out = []
    for nid in key_nutrients:
        t = tmeta.get(nid)
        if not t:
            continue
        segs = []
        total = 0.0
        for c in chosen_foods:
            amt = a.get(c["fdc_id"], {}).get(nid, 0) * c["grams"] / 100.0
            if amt > 1e-6:
                segs.append({"label": c["label"], "fdc_id": c["fdc_id"], "amount": round(amt, 1)})
                total += amt
        segs.sort(key=lambda s: -s["amount"])
        tgt = t["target"]
        for s in segs:
            s["pct_of_target"] = round(100 * s["amount"] / tgt) if tgt else 0
        out.append({
            "nutrient": t["name"], "unit": t["unit"], "nid": nid,
            "target": tgt, "total": round(total, 1),
            "pct": round(100 * total / tgt) if tgt else 0,
            "segments": segs,
        })
    return out


def _package(prob, status, ids, x, grams, serving, label, a, targets, mode, portions=None):
    st = pulp.LpStatus[status]
    chosen = []
    if st == "Optimal":
        for f in ids:
            val = x[f].value() or 0
            if val > 1e-4:
                g = val * serving[f] if mode == "MILP" else val
                chosen.append({
                    "fdc_id": f, "label": label[f],
                    "grams": round(g, 1),
                    "servings": round(val, 2) if mode == "MILP" else None,
                    "household": _household(g, (portions or {}).get(f, [])),
                })
    chosen.sort(key=lambda c: -c["grams"])
    totals = {}
    for c in chosen:
        for nid, per100 in a[c["fdc_id"]].items():
            totals[nid] = totals.get(nid, 0) + per100 * c["grams"] / 100.0
    return {
        "status": st, "mode": mode, "foods": chosen,
        "energy": round(totals.get(ENERGY, 0)),
        "protein": round(totals.get(PROTEIN, 0)),
        "n_foods": len(chosen),
        "totals": {str(k): round(v, 1) for k, v in totals.items()},
        "contributions": contributions(chosen, a, targets),
    }
