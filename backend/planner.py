"""Search the finite breakfast/lunch/dinner space after filtering hard constraints."""
from itertools import product

from .storage import MEALS, NUTRIENTS, Invalid


MEAL_NAMES = dict(zip(MEALS, ("早餐", "午餐", "晚餐")))
PORTIONS = (0.75, 1, 1.25, 1.5, 1.75, 2)
MEAL_SHARES = (0.28, 0.38, 0.34)


def plan_meals(catalog, targets, intent, recent):
    goal_energy = targets["energy_center"]
    ranges = targets["ranges"]
    bounds = [(ranges[key]["min"], ranges[key]["max"], key) for key in NUTRIENTS]
    excluded = set(intent["excluded_ids"])
    options = {meal: [] for meal in MEALS}
    eligible_count = 0
    for dish in catalog:
        if excluded.intersection(i["id"] for i in dish["ingredients"]):
            continue
        if intent["vegetarian"] and any(i["category"] in {"meat", "seafood"} for i in dish["ingredients"]):
            continue
        if intent["no_spicy"] and dish["flavor"] == "微辣":
            continue
        eligible_count += 1
        meal = dish["meal"]
        for portion in PORTIONS:
            nutrients = tuple(dish[key] * portion for key in NUTRIENTS)
            share = nutrients[0] / goal_energy
            if not 0.17 <= share <= 0.52:
                continue
            cost = (
                0.9 * abs(share - MEAL_SHARES[MEALS.index(meal)])
                + (0 if dish["flavor"] == intent["flavor"] else 0.085)
                + 0.075 * min(recent.get(dish["id"], 0), 4)
                + 0.025 * abs(portion - 1)
            )
            options[meal].append((dish, portion, nutrients, cost))

    missing = [MEAL_NAMES[meal] for meal, options_for_meal in options.items() if not options_for_meal]
    if missing:
        raise Invalid(f"当前菜库无法为{'、'.join(missing)}提供符合忌口且份量合适的菜品。请补充可选菜品；忌口保持生效。")

    best = None
    best_score = None
    checked = 0
    for breakfast, lunch, dinner in product(*(options[meal] for meal in MEALS)):
        checked += 1
        totals = tuple(round(a + b + c, 1) for a, b, c in zip(breakfast[2], lunch[2], dinner[2]))
        gap = sum((max(lo - value, value - hi, 0) / hi) * (2 if key == "kcal" else 1)
                  for value, (lo, hi, key) in zip(totals, bounds))
        fit = breakfast[3] + lunch[3] + dinner[3] + 1.8 * abs(totals[0] - goal_energy) / goal_energy
        score = (gap, fit)
        if best_score is None or score < best_score:
            best_score, best = score, (breakfast, lunch, dinner, totals)

    meals = []
    for dish, portion, nutrients, _ in best[:3]:
        meals.append({
            "dish_id": dish["id"], "name": dish["name"], "meal": dish["meal"], "flavor": dish["flavor"],
            "description": dish["description"], "portions": portion, "grams": round(dish["grams"] * portion),
            "image_url": dish["image_url"], "nutrients": dict(zip(NUTRIENTS, map(lambda v: round(v, 1), nutrients))),
            "ingredients": [{"name": i["name"], "id": i["id"], "grams": round(i["grams"] * portion, 1)}
                            for i in dish["ingredients"]],
            "recent_count": recent.get(dish["id"], 0),
        })
    totals = dict(zip(NUTRIENTS, best[3]))
    deviations = [
        {"key": key, "label": ranges[key]["label"], "unit": ranges[key]["unit"], "actual": totals[key],
         "min": lo, "max": hi}
        for lo, hi, key in bounds if not lo <= totals[key] <= hi
    ]
    return {
        "status": "closest" if deviations else "matched", "meals": meals, "totals": totals,
        "deviations": deviations, "search": {"eligible_dishes": eligible_count, "combinations": checked},
    }
