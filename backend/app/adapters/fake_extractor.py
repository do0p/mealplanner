from collections.abc import Callable

from app.ports.recipe_extractor import ExtractedIngredient, ExtractedRecipe, RecipeExtractor


class FakeRecipeExtractor(RecipeExtractor):
    """Deterministic extractor for tests — returns a fixed list of recipes."""

    def __init__(self, recipes: list[ExtractedRecipe] | None = None) -> None:
        self._recipes = recipes or [
            ExtractedRecipe(
                title="Test Recipe",
                base_servings=4,
                ingredients=[
                    ExtractedIngredient(name="Flour", quantity=400.0, unit="g", category="pantry"),
                    ExtractedIngredient(name="Egg", quantity=2.0, unit="pcs", category="dairy"),
                ],
                steps=["Mix flour and eggs.", "Bake for 30 minutes."],
                source_pages="1",
                raw_source_text="Test Recipe\nFlour 400g\n2 Eggs\nMix flour and eggs.\nBake for 30 minutes.",
            )
        ]

    def is_available(self) -> bool:
        return True

    @property
    def supports_image_extraction(self) -> bool:
        return True

    def extract_from_image(self, data: bytes, on_progress=None) -> list:
        if on_progress:
            on_progress("extracting", 0, 1)
            on_progress("extracting", 1, 1)
        return self._recipes

    def extract_recipes(
        self,
        segments: list[tuple[int, str]],
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> list[ExtractedRecipe]:
        return self._recipes
