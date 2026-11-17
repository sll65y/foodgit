"""Reference ranges for the classroom planner, based on adult demo profiles."""

ACTIVITY_FACTORS = {"low": 1.2, "light": 1.375, "moderate": 1.55, "high": 1.725}
GOAL_ADJUSTMENT = {"maintain": 0, "lose": -200, "gain": 200}
LABELS = {"kcal": ("能量", "kcal"), "protein": ("蛋白质", "g"), "carbs": ("碳水", "g"), "fat": ("脂肪", "g")}


def calculate_targets(profile, goal=None, high_protein=False):
    goal = goal or profile["goal"]
    sex_constant = 5 if profile["sex"] == "male" else -161
    resting = 10 * profile["weight_kg"] + 6.25 * profile["height_cm"] - 5 * profile["age"] + sex_constant
    factor = ACTIVITY_FACTORS[profile["activity"]]
    energy = round(max(resting, resting * factor + GOAL_ADJUSTMENT[goal]))
    intervals = {
        "kcal": (energy * 0.92, energy * 1.08),
        "protein": (energy * (0.20 if high_protein else 0.10) / 4, energy * 0.35 / 4),
        "carbs": (energy * 0.45 / 4, energy * 0.65 / 4),
        "fat": (energy * 0.20 / 9, energy * 0.35 / 9),
    }
    return {
        "resting_energy": round(resting), "activity_factor": factor, "energy_center": energy, "goal": goal,
        "ranges": {
            key: {"min": round(lo, 1), "max": round(hi, 1), "label": LABELS[key][0], "unit": LABELS[key][1]}
            for key, (lo, hi) in intervals.items()
        },
    }
