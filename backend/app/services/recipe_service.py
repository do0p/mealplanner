from pathlib import Path

from sqlmodel import Session, select

from app.config import settings
from app.models import (
    Ingredient,
    IngredientRead,
    IngredientWrite,
    InstructionStep,
    Recipe,
    RecipeRead,
    RecipeSummary,
    RecipeUpdate,
    StepRead,
)


def _to_recipe_read(r: Recipe) -> RecipeRead:
    return RecipeRead(
        id=r.id,
        title=r.title,
        base_servings=r.base_servings,
        notes=r.notes,
        source_format=r.source_format,
        source_file=r.source_file,
        source_pages=r.source_pages,
        course=r.course,
        calories_per_person=r.calories_per_person,
        protein_per_person=r.protein_per_person,
        is_vegetarian=r.is_vegetarian,
        is_vegan=r.is_vegan,
        is_favourite=r.is_favourite,
        is_want_to_try=r.is_want_to_try,
        status=r.status,
        created_at=r.created_at,
        ingredients=[
            IngredientRead(
                id=i.id,
                name=i.name,
                quantity_per_person=i.quantity_per_person,
                unit=i.unit,
                category=i.category,
                raw_text=i.raw_text,
            )
            for i in r.ingredients
        ],
        steps=[StepRead(step_number=s.step_number, text=s.text) for s in r.steps],
    )


def list_recipes(session: Session, status: str | None = "accepted") -> list[RecipeSummary]:
    stmt = select(Recipe)
    if status and status != "all":
        stmt = stmt.where(Recipe.status == status)
    stmt = stmt.order_by(Recipe.title)
    return [
        RecipeSummary(
            id=r.id,
            title=r.title,
            base_servings=r.base_servings,
            course=r.course,
            calories_per_person=r.calories_per_person,
            protein_per_person=r.protein_per_person,
            is_vegetarian=r.is_vegetarian,
            is_vegan=r.is_vegan,
            is_favourite=r.is_favourite,
            is_want_to_try=r.is_want_to_try,
            status=r.status,
            created_at=r.created_at,
        )
        for r in session.exec(stmt).all()
    ]


def get_recipe(session: Session, recipe_id: int) -> RecipeRead | None:
    r = session.get(Recipe, recipe_id)
    if r is None:
        return None
    # Eagerly load relationships while session is still open.
    _ = r.ingredients
    _ = r.steps
    return _to_recipe_read(r)


def update_recipe(session: Session, recipe_id: int, data: RecipeUpdate) -> RecipeRead | None:
    r = session.get(Recipe, recipe_id)
    if r is None:
        return None
    if data.title is not None:
        r.title = data.title
    if data.base_servings is not None:
        r.base_servings = data.base_servings
    if data.notes is not None:
        r.notes = data.notes
    if data.course is not None:
        r.course = data.course
    if data.calories_per_person is not None:
        r.calories_per_person = data.calories_per_person
    if data.protein_per_person is not None:
        r.protein_per_person = data.protein_per_person
    if data.is_vegetarian is not None:
        r.is_vegetarian = data.is_vegetarian
    if data.is_vegan is not None:
        r.is_vegan = data.is_vegan
    if data.is_favourite is not None:
        r.is_favourite = data.is_favourite
    if data.is_want_to_try is not None:
        r.is_want_to_try = data.is_want_to_try
    if data.ingredients is not None:
        r.ingredients = [
            Ingredient(
                name=ing.name,
                quantity_per_person=ing.quantity_per_person,
                unit=ing.unit,
                category=ing.category,
                raw_text=ing.raw_text,
                sort_order=idx,
            )
            for idx, ing in enumerate(data.ingredients)
        ]
    if data.steps is not None:
        r.steps = [
            InstructionStep(step_number=idx + 1, text=text)
            for idx, text in enumerate(data.steps)
        ]
    session.add(r)
    session.commit()
    session.refresh(r)
    _ = r.ingredients
    _ = r.steps
    return _to_recipe_read(r)


def delete_recipe(session: Session, recipe_id: int) -> bool:
    r = session.get(Recipe, recipe_id)
    if r is None:
        return False
    session.delete(r)
    session.commit()
    return True


def get_source_path(recipe: Recipe) -> Path | None:
    if not recipe.source_file:
        return None
    return settings.uploads_dir / recipe.source_file
