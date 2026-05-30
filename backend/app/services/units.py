"""Deterministic metric conversion, scaling and rounding.

This is a pure, LLM-free module. It acts as the safety net over the LLM's own
metric conversion: whatever unit comes in, ingredient quantities are reduced to
the canonical metric units g / ml / pcs where possible.
"""
import math

CANON_MASS = "g"
CANON_VOLUME = "ml"
CANON_COUNT = "pcs"

# factor to convert 1 <unit> into the canonical metric unit
_MASS = {
    "g": 1.0, "gram": 1.0, "grams": 1.0, "gr": 1.0,
    "kg": 1000.0, "kilogram": 1000.0, "kilograms": 1000.0,
    "mg": 0.001, "milligram": 0.001, "milligrams": 0.001,
    "oz": 28.3495, "ounce": 28.3495, "ounces": 28.3495,
    "lb": 453.592, "lbs": 453.592, "pound": 453.592, "pounds": 453.592,
}
_VOLUME = {
    "ml": 1.0, "milliliter": 1.0, "milliliters": 1.0, "millilitre": 1.0, "millilitres": 1.0, "cc": 1.0,
    "l": 1000.0, "liter": 1000.0, "liters": 1000.0, "litre": 1000.0, "litres": 1000.0,
    "dl": 100.0, "deciliter": 100.0, "deciliters": 100.0,
    "cl": 10.0, "centiliter": 10.0, "centiliters": 10.0,
    "tsp": 5.0, "teaspoon": 5.0, "teaspoons": 5.0,
    "tbsp": 15.0, "tbs": 15.0, "tablespoon": 15.0, "tablespoons": 15.0,
    "cup": 240.0, "cups": 240.0,
    "fl oz": 29.5735, "floz": 29.5735, "fluid ounce": 29.5735, "fluid ounces": 29.5735,
    "pint": 473.176, "pints": 473.176, "pt": 473.176,
    "quart": 946.353, "quarts": 946.353, "qt": 946.353,
    "gallon": 3785.41, "gallons": 3785.41, "gal": 3785.41,
}
_COUNT = {
    "pcs", "pc", "piece", "pieces", "stück", "stueck", "stk", "stks",
    "count", "x", "ea", "each", "unit", "units",
}


def _clean(unit: str) -> str:
    return " ".join(unit.strip().lower().rstrip(".").split())


def _scaled(quantity: float | None, factor: float) -> float | None:
    return None if quantity is None else quantity * factor


def to_metric(quantity: float | None, unit: str | None) -> tuple[float | None, str | None]:
    """Reduce (quantity, unit) to canonical metric. Unconvertible units
    (pinch, bunch, clove, can, ...) are preserved as-is."""
    if unit is None or _clean(unit) == "":
        # a bare number is a count of things
        return (None, None) if quantity is None else (quantity, CANON_COUNT)
    u = _clean(unit)
    if u in _MASS:
        return _scaled(quantity, _MASS[u]), CANON_MASS
    if u in _VOLUME:
        return _scaled(quantity, _VOLUME[u]), CANON_VOLUME
    if u in _COUNT:
        return quantity, CANON_COUNT
    return quantity, u


def per_person(quantity: float | None, servings: int | None) -> float | None:
    """Normalize a book quantity (written for `servings` people) to per-1-person."""
    if quantity is None:
        return None
    if not servings or servings <= 0:
        return quantity
    return quantity / servings


def scale(quantity_per_person: float | None, people: int) -> float | None:
    if quantity_per_person is None:
        return None
    return quantity_per_person * people


def round_quantity(quantity: float | None, unit: str | None) -> float | None:
    """Round for practical shopping: countables up to whole units, g/ml to a
    sensible precision."""
    if quantity is None:
        return None
    if unit == CANON_COUNT:
        return float(math.ceil(quantity - 1e-9))
    if quantity >= 10:
        return float(round(quantity))
    return round(quantity, 1)


def format_quantity(quantity: float | None, unit: str | None) -> str:
    """Human-readable amount, e.g. '200 g', '3', '1.5 tbsp'. The count unit is
    omitted since the ingredient name already carries it ('3 eggs')."""
    if quantity is None:
        q = ""
    else:
        r = round_quantity(quantity, unit)
        q = str(int(r)) if float(r).is_integer() else str(r)
    unit_str = "" if unit in (None, CANON_COUNT) else unit
    return " ".join(p for p in (q, unit_str) if p)


def fahrenheit_to_celsius(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0
