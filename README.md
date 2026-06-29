# Convergent Diet — Nutrition Instrument

A personal nutrition gap-finder built on USDA FoodData Central. It is a
*gap-finder, not a meal-dictator*: it tells you where your intended diet falls
short of your personalized targets, so you choose the food and the tool checks
the bookkeeping.

## Run it (works immediately on sample data)

    pip install flask pulp
    python make_sample_data.py     # creates USDA-shaped sample CSVs in data/
    python app.py                  # open http://127.0.0.1:5000

## Use your real USDA data

1. Download FoodData Central "Foundation Foods" CSVs.
2. Delete the sample files in `data/` and copy in the real
   `food.csv`, `food_nutrient.csv`, `nutrient.csv`, `food_portion.csv`,
   `measure_unit.csv`. The loader reads the real schema directly.
3. Run the app once; the **Data presence** panel shows which of your staples
   were found. For any marked missing, look up the real `fdc_id` and update
   `repertoire.py`.

## Files

- `app.py`           Flask app + dashboard routes
- `data_loader.py`   reads USDA CSVs, does food→food_nutrient→nutrient join
- `targets.py`       personalized targets (honest about what scales vs. fixed)
- `repertoire.py`    your staple list + profile — the file you edit
- `make_sample_data.py`  generates sample data in the real USDA schema
- `templates/index.html` the dashboard

## What scales with your body, and what doesn't

- **Energy** scales (Mifflin-St Jeor, or Katch-McArdle when you enter DEXA lean mass).
- **Protein** scales with target body weight.
- **Vitamins & minerals** are fixed population RDAs — they do NOT change with
  your weight. The tool holds them fixed on purpose and shows you that it does.

## Next steps (not yet built)

- Bioavailability layer (iron, zinc, vitamin A conversion, folate, protein
  quality) with meal-context toggles and visible error bars.
- LP/MILP gap-closer: "your worst gap is X; the single best addition is Y."
- Feasibility prover: "can this repertoire meet all targets under your calorie cap?"

## Fixing staple ids (the resolver)

Seed ids can be wrong (they're guesses). To resolve every staple against your
REAL data at once:

    python resolve_staples.py

It name-matches each staple, prints a verification report with kcal/protein
snapshots, and writes a correct repertoire.json. Check the report — a wrong
match is obvious from the snapshot. If one is wrong, edit that spec's
include/exclude keywords in resolve_staples.py and re-run. Use `--dry` to
preview without writing.

## Where your data lives (persistence)

- **repertoire.json** — your chosen staples, servings, labels, tags. Written by
  the picker UI and the resolver. THIS is the live repertoire. Edit it through
  the /staples page, not by hand.
- **repertoire.py** — only the initial SEED, used once if repertoire.json is
  absent. You can ignore it after first run.
- **data/*.csv** — the USDA reference data (read-only; you don't edit it).

## Entering food by household measure (cups, cans, eggs)

On the dashboard, each food has a quantity box and a measure dropdown populated
from the USDA portion data (cup, oz, "1 large", "1 can drained", …). Enter
"0.25" and pick "cup" for a quarter cup; grams are computed for you and the
choice is saved to repertoire.json, so it's pre-filled next time. Pick "grams"
to enter weight directly. Foods with no portion data in USDA fall back to grams.

## Bioavailability (absorbed vs content)

The dashboard shows CONTENT (USDA's "what's in the food") and, for the nutrients
where absorption diverges sharply, an ABSORBED estimate with a low–high band:

- **Iron** — heme vs non-heme split; vitamin C and meat in the meal enhance
  non-heme absorption, phytate (unsoaked grains/legumes), tea/coffee, and big
  calcium loads inhibit it.
- **Zinc** — phytate:zinc ratio model.
- **Vitamin A** — carotenoid sources need fat to absorb; animal retinol is well used.
- **Folate** — food-folate bioavailability + cooking loss.
- **Protein** — digestibility/quality discount (plant < animal).

Use the "This meal's context" toggles to reflect what's on the plate together.
The gold mark on each bar is the absorbed estimate against your target; the bands
are wide on purpose, because real absorption varies several-fold by person and
meal. Read the band, not a single number. All other nutrients show content only,
because for them content is a fair proxy.

## Optimize page (LP / MILP / gap-finder)

Visit /optimize. Toggle the **solver** (LP = continuous grams, MILP = whole
servings) and the **method**:

- **Optimal day** — the leanest way to meet every nutrient floor under your
  calorie ceiling (the classic Stigler problem). Expect monotony: the answer
  often collapses onto 2–4 foods in large quantities. This is a DIAGNOSTIC, not
  a menu — it shows you what the math alone produces.
- **Gap-finder** — keep the foods YOU choose (enter grams under "what you're
  already eating") and the solver adds the smallest amount to close the
  remaining floors. This can't return an inedible answer, because you set the base.

**Exclude foods** with the checkboxes — your "no, not sardines-and-oatmeal" lever.
Re-solve and the answer routes around them.

When infeasible, the page reports WHICH floors are the obstacle (best reachable
%), so you learn where supplementation or a new food is structurally required.

The optimizer works on CONTENT (absorption is meal-dependent and would make the
program circular). Use the dashboard's absorbed view as the reality check on
whatever the optimizer proposes.

### Coming next
- Multi-meal split (2 meals + optional snack) with per-meal balance.
- Weekly optimization: several days of varied menus that jointly cover gaps
  without daily monotony.
- Multiple distinct solutions (permutations) to choose between.
