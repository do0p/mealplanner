import math

import pytest

from app.services import units


@pytest.mark.parametrize(
    "qty,unit,exp_qty,exp_unit",
    [
        (1, "cup", 1, "cup"),
        (2, "tbsp", 2, "tbsp"),
        (3, "tsp", 3, "tsp"),
        (1, "l", 1000.0, "ml"),
        (1, "dl", 100.0, "ml"),
        (1, "oz", 28.3495, "g"),
        (1, "lb", 453.592, "g"),
        (2, "kg", 2000.0, "g"),
        (500, "mg", 0.5, "g"),
        (3, "pieces", 3, "pcs"),
        (2, None, 2, "pcs"),
        (4, "", 4, "pcs"),
    ],
)
def test_to_metric_known_units(qty, unit, exp_qty, exp_unit):
    q, u = units.to_metric(qty, unit)
    assert u == exp_unit
    assert q == pytest.approx(exp_qty)


def test_to_metric_compound_oz_units():
    # "(13.5-ounce) can" — the real-world case that triggered this fix
    qty, unit = units.to_metric(0.5, "(13.5-ounce) can")
    assert unit == "g"
    assert qty == pytest.approx(0.5 * 13.5 * 28.3495, rel=1e-4)
    # plain "28-oz bag"
    qty, unit = units.to_metric(1, "28-oz bag")
    assert unit == "g"
    assert qty == pytest.approx(28 * 28.3495, rel=1e-4)
    # fluid ounces: "16-fl-oz bottle"
    qty, unit = units.to_metric(2, "16-fl-oz bottle")
    assert unit == "ml"
    assert qty == pytest.approx(2 * 16 * 29.5735, rel=1e-4)


def test_to_metric_preserves_unconvertible_units():
    assert units.to_metric(1, "pinch") == (1, "pinch")
    assert units.to_metric(2, "Cloves") == (2, "cloves")


def test_to_metric_none_quantity_none_unit():
    assert units.to_metric(None, None) == (None, None)


def test_to_metric_case_and_whitespace_insensitive():
    assert units.to_metric(1, " Cup ") == (1, "cup")
    assert units.to_metric(1, "TBSP.") == (1, "tbsp")
    assert units.to_metric(1, "DL") == (100.0, "ml")


def test_per_person_normalizes_by_servings():
    assert units.per_person(800, 4) == 200
    assert units.per_person(None, 4) is None
    # unknown / zero servings: leave the quantity as-is
    assert units.per_person(200, 0) == 200
    assert units.per_person(200, None) == 200


def test_scale_multiplies_by_people():
    assert units.scale(200, 3) == 600
    assert units.scale(None, 3) is None


def test_round_quantity_counts_round_up():
    assert units.round_quantity(0.75, "pcs") == 1.0
    assert units.round_quantity(3.0, "pcs") == 3.0
    assert units.round_quantity(2.1, "pcs") == 3.0


def test_round_quantity_mass_volume_precision():
    assert units.round_quantity(12.4, "g") == 12.0
    assert units.round_quantity(250.6, "ml") == 251.0
    assert units.round_quantity(4.25, "g") == 4.2


def test_format_quantity():
    assert units.format_quantity(200, "g") == "200 g"
    assert units.format_quantity(3, "pcs") == "3"
    assert units.format_quantity(None, "pcs") == ""
    # Non-metric: fractions
    assert units.format_quantity(1.5, "tbsp") == "1 1/2 tbsp"
    assert units.format_quantity(0.5, "cup") == "1/2 cup"
    assert units.format_quantity(0.25, "cup") == "1/4 cup"
    assert units.format_quantity(1.0 / 3, "cup") == "1/3 cup"
    assert units.format_quantity(2.0 / 3, "cup") == "2/3 cup"
    assert units.format_quantity(0.75, "cup") == "3/4 cup"
    assert units.format_quantity(2.5, "tbsp") == "2 1/2 tbsp"
    # LLM-rounded approximations
    assert units.format_quantity(0.3, "cup") == "1/3 cup"
    assert units.format_quantity(0.6, "cup") == "2/3 cup"
    # Metric: no fractions
    assert units.format_quantity(0.5, "g") == "0.5 g"
    assert units.format_quantity(150.5, "ml") == "150 ml"  # rounded to nearest 5


def test_fahrenheit_to_celsius():
    assert units.fahrenheit_to_celsius(350) == pytest.approx(176.666, abs=1e-3)
    assert math.isclose(units.fahrenheit_to_celsius(32), 0.0)


def test_convert_step_text():
    assert units.convert_step_text("Bake at 375°F for 30 minutes.") == "Bake at 190°C for 30 minutes."
    assert units.convert_step_text("Heat to 350 F until golden.") == "Heat to 180°C until golden."
    assert units.convert_step_text("Simmer at 100°C.") == "Simmer at 100°C."
    assert units.convert_step_text("No temperature here.") == "No temperature here."
    assert units.convert_step_text("Preheat to 400°F and 425°F.") == "Preheat to 200°C and 220°C."
    # inch → cm
    assert units.convert_step_text("Cut into 2-inch pieces.") == "Cut into 5 cm pieces."
    assert units.convert_step_text("Roll out to 1/4-inch thickness.") == "Roll out to 0.5 cm thickness."
    assert units.convert_step_text("A 1 inch layer.") == "A 2.5 cm layer."
    assert units.convert_step_text("8 inches in diameter.") == "20 cm in diameter."
    assert units.convert_step_text('Use a 12" pan.') == "Use a 30 cm pan."
    assert units.convert_step_text("No measurements here.") == "No measurements here."
    # oz → g
    assert units.convert_step_text("Add 4 oz of cream cheese.") == "Add 113 g of cream cheese."
    assert units.convert_step_text("Use a 13.5-ounce can of coconut milk.") == "Use a 383 g can of coconut milk."
    assert units.convert_step_text("Stir in 2 ounces of butter.") == "Stir in 57 g of butter."
    # fl oz → ml
    assert units.convert_step_text("Pour 8 fl oz of milk.") == "Pour 237 ml of milk."
    assert units.convert_step_text("Add 16 fluid ounces of stock.") == "Add 473 ml of stock."
