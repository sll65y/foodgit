from contextlib import contextmanager
from datetime import date
import hashlib
import secrets
import sqlite3
import time
from pathlib import Path

from .seed import DISHES, INGREDIENTS


MEALS = ("breakfast", "lunch", "dinner")
NUTRIENTS = ("kcal", "protein", "carbs", "fat")


class Invalid(ValueError):
    pass


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    return f"{salt}:{key.hex()}"


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Store:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def initialize(self):
        with self.connection() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
            if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                return
            db.executemany("INSERT INTO ingredients VALUES (?, ?, ?, ?, ?, ?)", [
                (i, *row) for i, row in enumerate(INGREDIENTS, 1)
            ])
            for i, (name, meal, flavor, text, ingredients) in enumerate(DISHES, 1):
                db.execute("INSERT INTO dishes VALUES (?, ?, ?, ?, ?, NULL)", (i, name, meal, flavor, text))
                db.executemany("INSERT INTO dish_ingredients VALUES (?, ?, ?)", [
                    (i, key, grams) for key, grams in ingredients.items()
                ])
            for i, username, role, name in [
                (1, "demo", "member", "小禾"), (2, "admin", "admin", "菜库管理员"),
            ]:
                db.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (i, username, password_hash("food-demo"), role))
                db.execute("INSERT INTO profiles VALUES (?, ?, 26, 'female', 165, 61, 'light', 'maintain', '清淡')",
                           (i, name))

    def login(self, username, password):
        with self.connection() as db:
            row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if not row or not secrets.compare_digest(row["password_hash"], password_hash(
                password, row["password_hash"].split(":")[0]
            )):
                return None
            now = int(time.time())
            token = secrets.token_urlsafe(32)
            db.execute("DELETE FROM sessions WHERE expires <= ?", (now,))
            db.execute("INSERT INTO sessions VALUES (?, ?, ?)", (token_hash(token), row["id"], now + 86400))
            return token

    def user(self, token):
        with self.connection() as db:
            row = db.execute(
                """SELECT users.id, username, role FROM sessions JOIN users ON users.id = sessions.user_id
                   WHERE token_hash = ? AND expires > ?""", (token_hash(token), int(time.time())),
            ).fetchone()
            return dict(row) if row else None

    def logout(self, token):
        with self.connection() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(token),))

    def profile(self, user_id):
        with self.connection() as db:
            row = dict(db.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,)).fetchone())
            row.pop("user_id")
            row["excluded_ingredients"] = [
                r[0] for r in db.execute("SELECT ingredient_id FROM profile_exclusions WHERE user_id = ?", (user_id,))
            ]
            return row

    def save_profile(self, user_id, profile):
        exclusions = set(profile["excluded_ingredients"])
        self.validate_ingredients(exclusions)
        with self.connection() as db:
            db.execute(
                """UPDATE profiles SET display_name=:display_name, age=:age, sex=:sex, height_cm=:height_cm,
                   weight_kg=:weight_kg, activity=:activity, goal=:goal, preferred_flavor=:preferred_flavor
                   WHERE user_id=:user_id""", {**profile, "user_id": user_id},
            )
            db.execute("DELETE FROM profile_exclusions WHERE user_id = ?", (user_id,))
            db.executemany("INSERT INTO profile_exclusions VALUES (?, ?)", [(user_id, key) for key in exclusions])

    def ingredients(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM ingredients ORDER BY id")]

    def validate_ingredients(self, ids):
        if set(ids) - {i["id"] for i in self.ingredients()}:
            raise Invalid("包含未知食材，请从食材列表选择。")

    def dishes(self, meal=None, query="", page=1, size=None):
        with self.connection() as db:
            filters = "WHERE (? IS NULL OR d.meal = ?) AND instr(d.name, ?) > 0"
            params = (meal, meal, query)
            count = db.execute(f"SELECT count(*) FROM dishes d {filters}", params).fetchone()[0]
            rows = db.execute(
                f"""SELECT d.*, n.grams, n.kcal, n.protein, n.carbs, n.fat
                    FROM dishes d JOIN dish_nutrition n ON d.id = n.dish_id
                    {filters} ORDER BY d.id LIMIT ? OFFSET ?""",
                (*params, size if size is not None else -1, (page - 1) * (size or 0)),
            ).fetchall()
            items = {row["id"]: dict(row, ingredients=[]) for row in rows}
            if items:
                # The subquery uses the same page and avoids one lookup per dish.
                links = db.execute(
                    f"""SELECT di.dish_id, i.id, i.name, i.category, di.grams
                        FROM dish_ingredients di JOIN ingredients i ON di.ingredient_id=i.id
                        WHERE di.dish_id IN (
                            SELECT d.id FROM dishes d {filters} ORDER BY d.id LIMIT ? OFFSET ?
                        ) ORDER BY i.id""",
                    (*params, size if size is not None else -1, (page - 1) * (size or 0)),
                )
                for link in links:
                    dish_id, *ingredient = link
                    items[dish_id]["ingredients"].append(dict(zip(("id", "name", "category", "grams"), ingredient)))
            for item in items.values():
                key = item.pop("image_key")
                item["image_url"] = f"/images/{key}" if key else None
            return list(items.values()), count

    def create_dish(self, dish):
        ids = [i["id"] for i in dish["ingredients"]]
        self.validate_ingredients(ids)
        if len(set(ids)) != len(ids):
            raise Invalid("同一道菜不能重复选择食材，请合并用量。")
        if sum(i["grams"] for i in dish["ingredients"]) > 1500:
            raise Invalid("一道菜的单份总重量不能超过 1500 克。")
        try:
            with self.connection() as db:
                dish_id = db.execute(
                    "INSERT INTO dishes(name, meal, flavor, description) VALUES (?, ?, ?, ?)",
                    (dish["name"], dish["meal"], dish["flavor"], dish["description"]),
                ).lastrowid
                db.executemany("INSERT INTO dish_ingredients VALUES (?, ?, ?)", [
                    (dish_id, i["id"], i["grams"]) for i in dish["ingredients"]
                ])
                return dish_id
        except sqlite3.IntegrityError as exc:
            raise Invalid("菜品名称已存在。") from exc

    def set_image(self, dish_id, key):
        with self.connection() as db:
            return bool(db.execute("UPDATE dishes SET image_key=? WHERE id=?", (key, dish_id)).rowcount)

    def records(self, user_id, page, size):
        with self.connection() as db:
            count = db.execute("SELECT count(*) FROM intake_records WHERE user_id=?", (user_id,)).fetchone()[0]
            rows = db.execute(
                """SELECT id, dish_id, dish_name, eaten_on, meal, portions, kcal, protein, carbs, fat
                   FROM intake_records WHERE user_id=? ORDER BY eaten_on DESC, id DESC LIMIT ? OFFSET ?""",
                (user_id, size, (page - 1) * size),
            )
            return [dict(r) for r in rows], count

    def log_meal(self, user_id, record):
        if record["eaten_on"] > date.today():
            raise Invalid("不能记录未来的就餐日期。")
        with self.connection() as db:
            cursor = db.execute(
                """INSERT INTO intake_records(user_id, dish_id, dish_name, eaten_on, meal, portions, kcal, protein, carbs, fat)
                   SELECT :user, d.id, d.name, :day, :meal, :portions, n.kcal*:portions,
                          n.protein*:portions, n.carbs*:portions, n.fat*:portions
                   FROM dishes d JOIN dish_nutrition n ON n.dish_id = d.id WHERE d.id = :dish""",
                dict(user=user_id, day=record["eaten_on"].isoformat(), meal=record["meal"],
                     portions=record["portions"], dish=record["dish_id"]),
            )
            if not cursor.rowcount:
                raise Invalid("菜品不存在。")
            return cursor.lastrowid

    def delete_record(self, user_id, record_id):
        with self.connection() as db:
            return bool(db.execute("DELETE FROM intake_records WHERE user_id=? AND id=?", (user_id, record_id)).rowcount)

    def recent_dishes(self, user_id, start, end):
        with self.connection() as db:
            return dict(db.execute(
                """SELECT dish_id, COUNT(*) FROM intake_records WHERE user_id=? AND eaten_on BETWEEN ? AND ?
                   GROUP BY dish_id""", (user_id, start, end),
            ).fetchall())

    def daily_meals(self, user_id, start, end):
        with self.connection() as db:
            rows = db.execute(
                """SELECT eaten_on, meal, entries, kcal, protein, carbs, fat FROM intake_daily_meals
                   WHERE user_id=? AND eaten_on BETWEEN ? AND ? ORDER BY eaten_on""",
                (user_id, start, end),
            )
            return [dict(row) for row in rows]
