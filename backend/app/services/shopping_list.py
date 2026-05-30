"""Pure, LLM-free shopping-list aggregation.

Given a set of recipe selections (each with a people count and per-person
ingredients), scale every ingredient, convert to metric, then aggregate by
(ingredient name, unit) across all selected recipes.
"""
from dataclasses import dataclass

from pydantic import BaseModel

from app.services import units

# Categories are rendered in this order; anything else is appended alphabetically.
_CATEGORY_ORDER = [
    "produce", "meat", "seafood", "fish", "dairy", "bakery",
    "pantry", "spices", "condiments", "frozen", "beverages", "other",
]
_OTHER = "Other"


@dataclass
class IngredientInput:
    name: str
    quantity_per_person: float | None
    unit: str | None
    category: str | None = None


@dataclass
class RecipeSelection:
    title: str
    people: int
    ingredients: list[IngredientInput]


class ShoppingItem(BaseModel):
    name: str
    quantity: float | None
    unit: str | None
    display: str
    category: str
    from_recipes: list[str]


class ShoppingCategory(BaseModel):
    category: str
    items: list[ShoppingItem]


class ShoppingList(BaseModel):
    categories: list[ShoppingCategory]


def _norm_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _category_sort_key(category: str) -> tuple[int, str]:
    key = category.strip().lower()
    if key in _CATEGORY_ORDER:
        return (_CATEGORY_ORDER.index(key), key)
    return (len(_CATEGORY_ORDER), key)


def build_shopping_list(selections: list[RecipeSelection]) -> ShoppingList:
    # accumulate by (normalized name, metric unit) so different units of the
    # same ingredient stay as separate, honest line items.
    acc: dict[tuple[str, str | None], dict] = {}
    order: list[tuple[str, str | None]] = []

    for sel in selections:
        for ing in sel.ingredients:
            scaled = units.scale(ing.quantity_per_person, sel.people)
            qty, unit = units.to_metric(scaled, ing.unit)
            key = (_norm_name(ing.name), unit)
            if key not in acc:
                acc[key] = {
                    "name": ing.name.strip(),
                    "unit": unit,
                    "category": (ing.category or "").strip() or _OTHER,
                    "quantity": None,
                    "from": [],
                }
                order.append(key)
            entry = acc[key]
            if qty is not None:
                entry["quantity"] = (entry["quantity"] or 0.0) + qty
            if sel.title not in entry["from"]:
                entry["from"].append(sel.title)

    # group into categories
    by_category: dict[str, list[ShoppingItem]] = {}
    for key in order:
        e = acc[key]
        rounded = units.round_quantity(e["quantity"], e["unit"])
        item = ShoppingItem(
            name=e["name"],
            quantity=rounded,
            unit=e["unit"],
            display=units.format_quantity(e["quantity"], e["unit"]),
            category=e["category"],
            from_recipes=e["from"],
        )
        by_category.setdefault(e["category"], []).append(item)

    categories = []
    for cat in sorted(by_category, key=_category_sort_key):
        items = sorted(by_category[cat], key=lambda i: i.name.lower())
        categories.append(ShoppingCategory(category=cat, items=items))

    return ShoppingList(categories=categories)
