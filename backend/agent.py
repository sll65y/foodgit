"""Local text interpreter → target tool → planning tool → explanation."""
from datetime import date, timedelta
import re
import unicodedata

from .nutrition import calculate_targets
from .planner import plan_meals
from .storage import Invalid


GOALS = {"维持": "maintain", "维持体重": "maintain", "减脂": "lose", "想减脂": "lose",
         "减重": "lose", "增重": "gain", "增肌": "gain", "想增肌": "gain"}
FLAVORS = {"清淡": "清淡", "清淡一点": "清淡", "口味清淡": "清淡", "家常": "家常",
           "家常一点": "家常", "微辣": "微辣", "微辣一点": "微辣"}
CATEGORIES = {
    "海鲜": {"seafood"}, "虾": {"shrimp"}, "鱼": {"fish"}, "鱼虾": {"seafood"},
    "奶制品": {"dairy"}, "乳制品": {"dairy"}, "鸡蛋": {"egg"}, "蛋类": {"egg"},
    "大豆": {"soy"}, "豆制品": {"soy"}, "坚果": {"tree_nut", "peanut"}, "花生": {"peanut"},
    "肉类": {"meat"}, "肉": {"meat"}, "小麦": {"wheat"},
}
ALIASES = {"牛奶": "低脂牛奶", "酸奶": "无糖酸奶", "鸡肉": "鸡胸肉", "豆浆": "无糖豆浆"}


def interpret(message, profile, ingredients, request):
    by_name = {i["name"]: i["id"] for i in ingredients}
    intent = {
        "goal": profile["goal"], "flavor": profile["preferred_flavor"], "vegetarian": request["vegetarian"],
        "high_protein": False, "no_spicy": False, "excluded_ids": set(profile["excluded_ingredients"]) | set(request["exclude"]),
    }
    normalized = unicodedata.normalize("NFKC", message).strip()
    parts = re.split(r"[,;。!?\n]+", normalized)
    active_exclusion = False
    unknown = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        part = re.sub(r"^(?:(?:请|帮我|我想要|我想|我|要|希望)\s*)+", "", part)
        if re.fullmatch(r"(?:安排|生成|做|规划|来)?\s*(?:一日|一天的?|今天的?|明天的?)?\s*(?:三餐|食谱|饮食(?:计划|规划)|餐单|菜单)", part):
            active_exclusion = False
            continue
        if part in GOALS:
            intent["goal"] = GOALS[part]
        elif part in FLAVORS:
            intent["flavor"] = FLAVORS[part]
        elif part in {"素食", "吃素", "蛋奶素", "不吃荤"}:
            intent["vegetarian"] = True
        elif part in {"高蛋白", "蛋白质高一点", "多一点蛋白质"}:
            intent["high_protein"] = True
        elif part in {"不辣", "不吃辣", "不要辣", "不放辣椒"}:
            intent["no_spicy"] = True
            intent["excluded_ids"].add(by_name["辣椒"])
        else:
            found = re.fullmatch(r"(?:不吃|不要|不放|不含|避免|忌口[: ]*|不能吃|无)(.+?)(?:过敏)?", part)
            suffix = re.fullmatch(r"(?:对)?(.+?)过敏", part)
            if found or suffix or active_exclusion:
                phrase = (found or suffix).group(1) if (found or suffix) else part
                active_exclusion = True
                for item in re.split(r"[、/]|和|及|与", phrase):
                    name = item.strip()
                    categories = CATEGORIES.get(name)
                    if categories:
                        intent["excluded_ids"].update(
                            i["id"] for i in ingredients if i["category"] in categories
                            or (name == "虾" and i["name"] == "虾仁")
                            or (name == "鱼" and i["name"] == "三文鱼")
                            or (name == "小麦" and i["name"] in {"全麦面包", "荞麦面"})
                        )
                    elif ALIASES.get(name, name) in by_name:
                        intent["excluded_ids"].add(by_name[ALIASES.get(name, name)])
                    else:
                        unknown.append(name)
                continue
            unknown.append(part)
        active_exclusion = False
    if unknown:
        raise Invalid(
            "暂不能确认这些要求：" + "、".join(f"「{part}」" for part in unknown)
            + "。请用逗号分开条件，例如「减脂，清淡一点，不吃花生」，或从忌口列表选择。"
        )
    intent["excluded_ids"] = sorted(intent["excluded_ids"])
    names = {i["id"]: i["name"] for i in ingredients}
    intent["excluded_names"] = [names[key] for key in intent["excluded_ids"]]
    return intent


def generate_plan(store, user_id, request, today=None):
    today = today or date.today()
    profile = store.profile(user_id)
    store.validate_ingredients(request["exclude"])
    intent = interpret(request["message"], profile, store.ingredients(), request)
    targets = calculate_targets(profile, intent["goal"], intent["high_protein"])
    recent = store.recent_dishes(user_id, (today - timedelta(days=6)).isoformat(), today.isoformat())
    plan = plan_meals(store.dishes()[0], targets, intent, recent)
    explanation = [
        f"按当前画像估算每日能量，以 {targets['energy_center']} kcal 为规划中心。",
        (f"已排除菜谱中含{'、'.join(intent['excluded_names'])}的菜品。"
         if intent["excluded_names"] else "本次没有选择单独的忌口食材。"),
    ]
    if intent["vegetarian"]:
        explanation.append("采用蛋奶素条件，排除肉类和海鲜。")
    if recent:
        explanation.append(f"参与排序的近 7 天饮食记录共 {sum(recent.values())} 条，优先减少重复菜品。")
    flavor_count = sum(meal["flavor"] == intent["flavor"] for meal in plan["meals"])
    explanation.append(f"三餐中有 {flavor_count} 餐符合「{intent['flavor']}」口味偏好。")
    if plan["deviations"]:
        misses = "、".join(d["label"] for d in plan["deviations"])
        explanation.append(f"当前候选中找不到所有营养项都在区间内的组合；这份近似方案的{misses}超出目标范围。")
    return {
        **plan, "request": request["message"], "intent": intent, "targets": targets,
        "explanation": explanation,
        "tools": ["interpret_request", "calculate_targets", "plan_meals"],
    }
