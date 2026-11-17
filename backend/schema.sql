CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('member', 'admin'))
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    age INTEGER NOT NULL,
    sex TEXT NOT NULL,
    height_cm REAL NOT NULL,
    weight_kg REAL NOT NULL,
    activity TEXT NOT NULL,
    goal TEXT NOT NULL,
    preferred_flavor TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ingredients (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    protein_100g REAL NOT NULL,
    carbs_100g REAL NOT NULL,
    fat_100g REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS profile_exclusions (
    user_id INTEGER NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
    ingredient_id INTEGER NOT NULL REFERENCES ingredients(id),
    PRIMARY KEY (user_id, ingredient_id)
);
CREATE TABLE IF NOT EXISTS dishes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    meal TEXT NOT NULL CHECK (meal IN ('breakfast', 'lunch', 'dinner')),
    flavor TEXT NOT NULL,
    description TEXT NOT NULL,
    image_key TEXT
);
CREATE TABLE IF NOT EXISTS dish_ingredients (
    dish_id INTEGER NOT NULL REFERENCES dishes(id),
    ingredient_id INTEGER NOT NULL REFERENCES ingredients(id),
    grams INTEGER NOT NULL CHECK (grams > 0),
    PRIMARY KEY (dish_id, ingredient_id)
);
CREATE VIEW IF NOT EXISTS dish_nutrition AS
SELECT dish_id, SUM(grams) AS grams,
       SUM(grams * (protein_100g * 4 + carbs_100g * 4 + fat_100g * 9) / 100) AS kcal,
       SUM(grams * protein_100g / 100) AS protein,
       SUM(grams * carbs_100g / 100) AS carbs,
       SUM(grams * fat_100g / 100) AS fat
FROM dish_ingredients JOIN ingredients ON ingredients.id = dish_ingredients.ingredient_id
GROUP BY dish_id;

CREATE TABLE IF NOT EXISTS intake_records (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    dish_id INTEGER NOT NULL REFERENCES dishes(id),
    dish_name TEXT NOT NULL,
    eaten_on TEXT NOT NULL,
    meal TEXT NOT NULL CHECK (meal IN ('breakfast', 'lunch', 'dinner')),
    portions REAL NOT NULL CHECK (portions > 0),
    kcal REAL NOT NULL,
    protein REAL NOT NULL,
    carbs REAL NOT NULL,
    fat REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intake_user_date ON intake_records(user_id, eaten_on DESC, id DESC);
CREATE TABLE IF NOT EXISTS intake_daily_meals (
    user_id INTEGER NOT NULL REFERENCES users(id),
    eaten_on TEXT NOT NULL,
    meal TEXT NOT NULL,
    entries INTEGER NOT NULL,
    kcal REAL NOT NULL,
    protein REAL NOT NULL,
    carbs REAL NOT NULL,
    fat REAL NOT NULL,
    PRIMARY KEY (user_id, eaten_on, meal)
);
CREATE TRIGGER IF NOT EXISTS intake_after_insert
AFTER INSERT ON intake_records
BEGIN
    INSERT INTO intake_daily_meals
    VALUES (NEW.user_id, NEW.eaten_on, NEW.meal, 1, NEW.kcal, NEW.protein, NEW.carbs, NEW.fat)
    ON CONFLICT(user_id, eaten_on, meal) DO UPDATE SET
        entries = entries + 1, kcal = kcal + NEW.kcal, protein = protein + NEW.protein,
        carbs = carbs + NEW.carbs, fat = fat + NEW.fat;
END;
CREATE TRIGGER IF NOT EXISTS intake_after_delete
AFTER DELETE ON intake_records
BEGIN
    UPDATE intake_daily_meals SET entries = entries - 1, kcal = kcal - OLD.kcal,
        protein = protein - OLD.protein, carbs = carbs - OLD.carbs, fat = fat - OLD.fat
    WHERE user_id = OLD.user_id AND eaten_on = OLD.eaten_on AND meal = OLD.meal;
    DELETE FROM intake_daily_meals
    WHERE user_id = OLD.user_id AND eaten_on = OLD.eaten_on AND meal = OLD.meal AND entries = 0;
END;
