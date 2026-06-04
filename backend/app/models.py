from datetime import datetime, timezone

from pydantic import BaseModel
from sqlmodel import Field, Relationship, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


RECIPE_ACCEPTED = "accepted"

# Ingredients that cannot be meaningfully split below 1 unit (e.g. 0.5 eggs
# makes no sense). Matched against any word in the ingredient name (lowercase).
# Extend this list without re-importing recipes — it is evaluated at serve time.
WHOLE_UNIT_INGREDIENTS: frozenset[str] = frozenset({"egg", "eggs"})

JOB_PENDING = "pending"
JOB_PROCESSING = "processing"
JOB_COMPLETED = "completed"
JOB_FAILED = "failed"


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------
class Ingredient(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    recipe_id: int = Field(foreign_key="recipe.id", index=True)
    name: str
    # Quantities are normalized to PER ONE PERSON; scale by * people at use time.
    quantity_per_person: float | None = None
    unit: str | None = None  # canonical metric: "g", "ml", "pcs", or None
    category: str | None = None  # e.g. produce, dairy — for shopping-list grouping
    raw_text: str | None = None  # original line from the source, for provenance
    sort_order: int = 0

    recipe: "Recipe" = Relationship(back_populates="ingredients")


class InstructionStep(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    recipe_id: int = Field(foreign_key="recipe.id", index=True)
    step_number: int
    text: str  # copied verbatim from the source

    recipe: "Recipe" = Relationship(back_populates="steps")


class Recipe(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    base_servings: int | None = None  # original "serves N" — provenance only
    notes: str | None = None

    source_format: str | None = None  # detected format, e.g. "pdf"
    source_file: str | None = None  # stored filename under uploads dir
    source_pages: str | None = None  # e.g. "12-14"
    raw_source_text: str | None = None  # source text the recipe was extracted from

    import_job_id: int | None = Field(default=None, foreign_key="importjob.id", index=True)

    course: str | None = None  # breakfast/appetizer/soup/salad/main/side/dessert/snack/beverage
    calories_per_person: float | None = None
    protein_per_person: float | None = None
    fat_per_person: float | None = None
    carbs_per_person: float | None = None

    is_vegetarian: bool = Field(default=False)
    is_vegan: bool = Field(default=False)
    is_favourite: bool = Field(default=False)
    is_want_to_try: bool = Field(default=False)

    status: str = RECIPE_ACCEPTED
    created_at: datetime = Field(default_factory=_now)

    ingredients: list[Ingredient] = Relationship(
        back_populates="recipe",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "Ingredient.sort_order"},
    )
    steps: list[InstructionStep] = Relationship(
        back_populates="recipe",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "InstructionStep.step_number"},
    )


class MealPlan(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=_now)

    entries: list["MealPlanEntry"] = Relationship(
        back_populates="plan",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "MealPlanEntry.sort_order"},
    )


class MealPlanEntry(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="mealplan.id", index=True)
    recipe_id: int = Field(foreign_key="recipe.id", index=True)
    slot: str  # free-form slot label, e.g. "Mon-dinner"
    people: int = 2
    sort_order: int = 0

    plan: MealPlan = Relationship(back_populates="entries")


class ImportJob(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    filename: str  # original uploaded name
    stored_file: str  # filename under uploads dir
    source_format: str
    status: str = JOB_PENDING
    error: str | None = None
    recipe_count: int = 0
    progress_current: int = 0
    progress_total: int = 0
    phase: str | None = None  # segmenting | extracting
    created_at: datetime = Field(default_factory=_now)
    processed_at: datetime | None = None


# --------------------------------------------------------------------------
# Read / write API schemas (decoupled from table rows so nested data is safe
# to serialize after the session closes).
# --------------------------------------------------------------------------
class IngredientRead(BaseModel):
    id: int
    name: str
    quantity_per_person: float | None
    unit: str | None
    category: str | None
    raw_text: str | None
    whole_unit_only: bool = False


class StepRead(BaseModel):
    step_number: int
    text: str


class RecipeRead(BaseModel):
    id: int
    title: str
    base_servings: int | None
    notes: str | None
    source_format: str | None
    source_file: str | None
    source_pages: str | None
    course: str | None
    calories_per_person: float | None
    protein_per_person: float | None
    fat_per_person: float | None
    carbs_per_person: float | None
    is_vegetarian: bool
    is_vegan: bool
    is_favourite: bool
    is_want_to_try: bool
    status: str
    created_at: datetime
    ingredients: list[IngredientRead]
    steps: list[StepRead]


class RecipeSummary(BaseModel):
    id: int
    title: str
    base_servings: int | None
    course: str | None
    calories_per_person: float | None
    protein_per_person: float | None
    fat_per_person: float | None
    carbs_per_person: float | None
    is_vegetarian: bool
    is_vegan: bool
    is_favourite: bool
    is_want_to_try: bool
    status: str
    created_at: datetime


class IngredientWrite(BaseModel):
    name: str
    quantity_per_person: float | None = None
    unit: str | None = None
    category: str | None = None
    raw_text: str | None = None


class RecipeCreate(BaseModel):
    title: str
    base_servings: int | None = None
    notes: str | None = None
    course: str | None = None
    calories_per_person: float | None = None
    protein_per_person: float | None = None
    fat_per_person: float | None = None
    carbs_per_person: float | None = None
    is_vegetarian: bool = False
    is_vegan: bool = False
    is_favourite: bool = False
    is_want_to_try: bool = False
    ingredients: list[IngredientWrite] = []
    steps: list[str] = []


class RecipeUpdate(BaseModel):
    title: str | None = None
    base_servings: int | None = None
    notes: str | None = None
    course: str | None = None
    calories_per_person: float | None = None
    protein_per_person: float | None = None
    fat_per_person: float | None = None
    carbs_per_person: float | None = None
    is_vegetarian: bool | None = None
    is_vegan: bool | None = None
    is_favourite: bool | None = None
    is_want_to_try: bool | None = None
    ingredients: list[IngredientWrite] | None = None
    steps: list[str] | None = None


# --- Plans ---

class EntryWrite(BaseModel):
    recipe_id: int
    slot: str
    people: int = 2
    sort_order: int = 0


class PlanCreate(BaseModel):
    name: str


class PlanUpdate(BaseModel):
    name: str | None = None
    entries: list[EntryWrite] | None = None


class PlanEntryRead(BaseModel):
    id: int
    recipe_id: int
    recipe_title: str
    slot: str
    people: int
    sort_order: int


class PlanRead(BaseModel):
    id: int
    name: str
    created_at: datetime
    entries: list[PlanEntryRead]


class PlanSummary(BaseModel):
    id: int
    name: str
    created_at: datetime
    entry_count: int


# --- Import jobs ---

class ImportJobSummary(BaseModel):
    id: int
    filename: str
    source_format: str
    status: str
    error: str | None
    recipe_count: int
    progress_current: int
    progress_total: int
    phase: str | None
    created_at: datetime
    processed_at: datetime | None


class ImportJobRead(BaseModel):
    id: int
    filename: str
    source_format: str
    status: str
    error: str | None
    recipe_count: int
    progress_current: int
    progress_total: int
    phase: str | None
    created_at: datetime
    processed_at: datetime | None
    recipes: list[RecipeSummary]


