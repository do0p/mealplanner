from sqlmodel import Session, select

from app.models import (
    EntryWrite,
    MealPlan,
    MealPlanEntry,
    PlanCreate,
    PlanEntryRead,
    PlanRead,
    PlanSummary,
    PlanUpdate,
    Recipe,
)
from app.services.shopping_list import (
    IngredientInput,
    RecipeSelection,
    ShoppingList,
    build_shopping_list,
)


def _entry_read(e: MealPlanEntry, title: str) -> PlanEntryRead:
    return PlanEntryRead(
        id=e.id,
        recipe_id=e.recipe_id,
        recipe_title=title,
        slot=e.slot,
        people=e.people,
        sort_order=e.sort_order,
    )


def _to_plan_read(session: Session, plan: MealPlan) -> PlanRead:
    _ = plan.entries
    entries = []
    for e in plan.entries:
        r = session.get(Recipe, e.recipe_id)
        entries.append(_entry_read(e, r.title if r else f"Recipe {e.recipe_id}"))
    entries.sort(key=lambda e: e.sort_order)
    return PlanRead(
        id=plan.id,
        name=plan.name,
        created_at=plan.created_at,
        entries=entries,
    )


def list_plans(session: Session) -> list[PlanSummary]:
    plans = session.exec(select(MealPlan).order_by(MealPlan.created_at.desc())).all()
    return [
        PlanSummary(
            id=p.id,
            name=p.name,
            created_at=p.created_at,
            entry_count=len(p.entries),
        )
        for p in plans
    ]


def create_plan(session: Session, data: PlanCreate) -> PlanRead:
    plan = MealPlan(name=data.name)
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return _to_plan_read(session, plan)


def get_plan(session: Session, plan_id: int) -> PlanRead | None:
    plan = session.get(MealPlan, plan_id)
    if plan is None:
        return None
    return _to_plan_read(session, plan)


def update_plan(session: Session, plan_id: int, data: PlanUpdate) -> PlanRead | None:
    plan = session.get(MealPlan, plan_id)
    if plan is None:
        return None
    if data.name is not None:
        plan.name = data.name
    if data.entries is not None:
        plan.entries = [
            MealPlanEntry(
                recipe_id=e.recipe_id,
                slot=e.slot,
                people=e.people,
                sort_order=e.sort_order,
            )
            for e in data.entries
        ]
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return _to_plan_read(session, plan)


def delete_plan(session: Session, plan_id: int) -> bool:
    plan = session.get(MealPlan, plan_id)
    if plan is None:
        return False
    session.delete(plan)
    session.commit()
    return True


def get_shopping_list(session: Session, plan_id: int) -> ShoppingList | None:
    plan = session.get(MealPlan, plan_id)
    if plan is None:
        return None
    _ = plan.entries
    selections = []
    for entry in plan.entries:
        recipe = session.get(Recipe, entry.recipe_id)
        if recipe is None:
            continue
        _ = recipe.ingredients
        selections.append(
            RecipeSelection(
                title=recipe.title,
                people=entry.people,
                ingredients=[
                    IngredientInput(
                        name=ing.name,
                        quantity_per_person=ing.quantity_per_person,
                        unit=ing.unit,
                        category=ing.category,
                    )
                    for ing in recipe.ingredients
                ],
            )
        )
    return build_shopping_list(selections)
