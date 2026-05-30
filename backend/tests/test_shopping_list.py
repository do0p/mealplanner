from app.services.shopping_list import (
    IngredientInput,
    RecipeSelection,
    build_shopping_list,
)


def _find(sl, name):
    for cat in sl.categories:
        for item in cat.items:
            if item.name.lower() == name.lower():
                return item
    return None


def test_scaling_by_people():
    sel = RecipeSelection(
        title="Soup",
        people=4,
        ingredients=[IngredientInput("Flour", 50, "g", "pantry")],
    )
    sl = build_shopping_list([sel])
    item = _find(sl, "Flour")
    assert item.quantity == 200.0  # 50 g/person * 4
    assert item.unit == "g"


def test_same_ingredient_same_unit_is_summed_across_recipes():
    a = RecipeSelection("A", 2, [IngredientInput("Onion", 0.5, None, "produce")])
    b = RecipeSelection("B", 3, [IngredientInput("onion", 0.5, "pcs", "produce")])
    sl = build_shopping_list([a, b])
    onion = _find(sl, "Onion")
    # (0.5*2) + (0.5*3) = 2.5 pcs -> round up to 3
    assert onion.quantity == 3.0
    assert onion.unit == "pcs"
    assert set(onion.from_recipes) == {"A", "B"}


def test_different_units_same_name_stay_separate():
    a = RecipeSelection("A", 1, [IngredientInput("Tomato", 2, None, "produce")])
    b = RecipeSelection("B", 1, [IngredientInput("Tomato", 100, "g", "produce")])
    sl = build_shopping_list([a, b])
    units_seen = {
        item.unit
        for cat in sl.categories
        for item in cat.items
        if item.name.lower() == "tomato"
    }
    assert units_seen == {"pcs", "g"}


def test_no_quantity_ingredient_listed_once_without_amount():
    a = RecipeSelection("A", 2, [IngredientInput("Salt", None, None, "spices")])
    b = RecipeSelection("B", 4, [IngredientInput("salt", None, None, "spices")])
    sl = build_shopping_list([a, b])
    salt = _find(sl, "Salt")
    assert salt.quantity is None
    assert salt.display == ""
    assert set(salt.from_recipes) == {"A", "B"}


def test_imperial_converted_then_aggregated():
    a = RecipeSelection("A", 2, [IngredientInput("Milk", 1, "cup", "dairy")])
    sl = build_shopping_list([a])
    milk = _find(sl, "Milk")
    assert milk.unit == "cup"
    assert milk.quantity == 2.0  # 1 cup/person * 2 people


def test_category_grouping_and_order():
    sels = [
        RecipeSelection("A", 1, [
            IngredientInput("Apple", 1, None, "produce"),
            IngredientInput("Milk", 100, "ml", "dairy"),
            IngredientInput("Mystery", 1, None, None),
        ]),
    ]
    sl = build_shopping_list(sels)
    cats = [c.category for c in sl.categories]
    assert cats.index("produce") < cats.index("dairy") < cats.index("Other")
