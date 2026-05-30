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
    assert units.format_quantity(1.5, "tbsp") == "1.5 tbsp"


def test_fahrenheit_to_celsius():
    assert units.fahrenheit_to_celsius(350) == pytest.approx(176.666, abs=1e-3)
    assert math.isclose(units.fahrenheit_to_celsius(32), 0.0)


def test_convert_step_text():
    assert units.convert_step_text("Bake at 375°F for 30 minutes.") == "Bake at 190°C for 30 minutes."
    assert units.convert_step_text("Heat to 350 F until golden.") == "Heat to 180°C until golden."
    assert units.convert_step_text("Simmer at 100°C.") == "Simmer at 100°C."
    assert units.convert_step_text("No temperature here.") == "No temperature here."
    assert units.convert_step_text("Preheat to 400°F and 425°F.") == "Preheat to 200°C and 220°C."
