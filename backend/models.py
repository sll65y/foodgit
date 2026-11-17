from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Meal = Literal["breakfast", "lunch", "dinner"]
Flavor = Literal["清淡", "家常", "微辣"]
Goal = Literal["maintain", "lose", "gain"]
PositiveId = Annotated[int, Field(gt=0, le=2_147_483_647)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=48)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class Login(Input):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)


class Profile(Input):
    display_name: Name
    age: int = Field(ge=19, le=78)
    sex: Literal["female", "male"]
    height_cm: float = Field(ge=130, le=220)
    weight_kg: float = Field(ge=40, le=200)
    activity: Literal["low", "light", "moderate", "high"]
    goal: Goal
    preferred_flavor: Flavor
    excluded_ingredients: list[PositiveId] = Field(max_length=100)


class PlanRequest(Input):
    message: str = Field(default="", max_length=300)
    exclude: list[PositiveId] = Field(default_factory=list, max_length=100)
    vegetarian: bool = False


class Record(Input):
    dish_id: PositiveId
    meal: Meal
    eaten_on: date
    portions: float = Field(gt=0, le=5)


class RecipeIngredient(Input):
    id: PositiveId
    grams: int = Field(gt=0, le=1000)


class DishInput(Input):
    name: Name
    meal: Meal
    flavor: Flavor
    description: str = Field(max_length=160)
    ingredients: list[RecipeIngredient] = Field(min_length=1, max_length=25)
