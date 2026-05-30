from abc import ABC, abstractmethod
from collections.abc import Callable

from pydantic import BaseModel


class ExtractedIngredient(BaseModel):
    name: str
    quantity: float | None = None  # book quantity (before per-person normalization)
    unit: str | None = None
    category: str | None = None
    raw_text: str | None = None


class ExtractedRecipe(BaseModel):
    title: str
    base_servings: int | None = None
    ingredients: list[ExtractedIngredient] = []
    steps: list[str] = []  # instruction text, verbatim
    source_pages: str | None = None
    notes: str | None = None
    raw_source_text: str | None = None
    course: str | None = None  # breakfast/appetizer/soup/salad/main/side/dessert/snack/beverage
    calories_total: float | None = None          # estimated total kcal for the whole recipe
    protein_total: float | None = None           # estimated total protein (g) for the whole recipe
    calories_per_serving_stated: float | None = None  # explicitly stated per-serving kcal from the text
    protein_per_serving_stated: float | None = None   # explicitly stated per-serving protein (g) from the text


class RecipeExtractor(ABC):

    @abstractmethod
    def is_available(self) -> bool:
        """Probe the underlying service. Must not raise; return False if unreachable."""
        ...

    @abstractmethod
    def extract_recipes(
        self,
        segments: list[tuple[int, str]],
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> list[ExtractedRecipe]:
        """Given (page_number, text) segments from one document, return all
        recipes found — one item for a single-recipe doc, many for a cookbook.
        on_progress(phase, current, total) is called at each phase transition."""
        ...

    @property
    def supports_image_extraction(self) -> bool:
        return False

    def extract_from_image(
        self,
        data: bytes,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> list[ExtractedRecipe]:
        raise NotImplementedError(f"{self.__class__.__name__} does not support image extraction")
