"""Provider-independent schemas and deterministic business rules."""

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Location = Literal["fridge", "freezer", "pantry", "other"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ItemIn(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    bought_date: date
    shelf_days: int = Field(ge=0, le=3650, strict=True)
    location: Location


class DraftItem(StrictModel):
    name: str | None
    bought_date: date | None
    shelf_days: int | None = Field(ge=0, le=3650)
    location: Location | None
    quantity_text: str | None
    clarification: str | None
    expiry_date_hint: date | None = None


class Extraction(StrictModel):
    items: list[DraftItem] = Field(max_length=50)


class ItemsIn(StrictModel):
    items: list[ItemIn] = Field(min_length=1, max_length=50)


class ItemPatch(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    bought_date: date | None = None
    shelf_days: int | None = Field(default=None, ge=0, le=3650, strict=True)
    location: Location | None = None
    status: Literal["active", "used"] | None = None

    @field_validator("*", mode="before")
    @classmethod
    def no_explicit_null(cls, value):
        if value is None:
            raise ValueError("A supplied update field cannot be null")
        return value


class Meal(StrictModel):
    dish: str = Field(min_length=1, max_length=200)
    items_used: list[str] = Field(min_length=1, max_length=30)
    steps: list[str] = Field(min_length=1, max_length=20)
    priority_items: list[str]


class MealPlan(StrictModel):
    breakfast: Meal
    lunch: Meal
    dinner: Meal


BASICS = {"salt", "oil", "water", "spices"}


def days_left(item: dict, today: date) -> int:
    return (date.fromisoformat(str(item["expiry_date"])) - today).days


def level_for(days: int) -> str | None:
    if days < 0:
        return "expired"
    if days <= 1:
        return "high"
    if days <= 3:
        return "moderate"
    if days <= 7:
        return "slight"
    return None


def add_days(bought: str, shelf_days: int) -> str:
    return (date.fromisoformat(bought) + timedelta(days=shelf_days)).isoformat()


def inventory_context(items: list[dict], today: date):
    active = sorted(
        (
            i
            for i in items
            if i.get("status", "active") == "active" and days_left(i, today) >= 0
        ),
        key=lambda i: i["expiry_date"],
    )
    priority = [i["name"] for i in active if days_left(i, today) <= 3]
    return active, priority


def validate_plan(
    plan: MealPlan, inventory: list[dict], priority: list[str]
) -> MealPlan:
    names = {i["name"].casefold() for i in inventory}
    wanted = {n.casefold() for n in priority}
    for meal in (plan.breakfast, plan.lunch, plan.dinner):
        used = {n.strip().casefold() for n in meal.items_used}
        reported = {n.strip().casefold() for n in meal.priority_items}
        if not used <= names | BASICS:
            raise ValueError(
                "Meal includes ingredients outside pantry and allowed basics"
            )
        covered = used & wanted
        if wanted and not covered:
            raise ValueError("Every meal must use a priority ingredient")
        if reported != covered:
            raise ValueError(
                "Reported priority ingredients do not match ingredients used"
            )
        if any(not step.strip() for step in meal.steps):
            raise ValueError("Instructions cannot be empty")
    return plan


def item_view(item: dict, today: date):
    d = days_left(item, today)
    return {
        **item,
        "days_left": d,
        "level": level_for(d) if item["status"] == "active" else None,
        "status": "expired" if item["status"] == "active" and d < 0 else item["status"],
    }


def expiry_preview(items: list[dict], today: date):
    return [item_view(i, today) for i in items]
