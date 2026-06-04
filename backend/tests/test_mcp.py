"""Tests for the MCP server tools using an in-memory SQLite DB."""
import asyncio
import json
import os

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app import models


@pytest.fixture(autouse=True)
def in_memory_db(tmp_path, monkeypatch):
    """Point the MCP server's engine at a fresh in-memory DB for each test."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)

    import app.mcp_server as mcp_mod
    monkeypatch.setattr(mcp_mod, "engine", eng)
    return eng


def _add_recipe(engine, **kwargs) -> models.Recipe:
    with Session(engine) as s:
        r = models.Recipe(
            title=kwargs.get("title", "Pasta"),
            base_servings=kwargs.get("base_servings", 2),
            course=kwargs.get("course", "main"),
            is_vegetarian=kwargs.get("is_vegetarian", False),
            is_vegan=kwargs.get("is_vegan", False),
            is_favourite=kwargs.get("is_favourite", False),
            status=models.RECIPE_ACCEPTED,
        )
        for idx, ing in enumerate(kwargs.get("ingredients", [])):
            r.ingredients.append(
                models.Ingredient(
                    name=ing["name"],
                    quantity_per_person=ing.get("quantity_per_person"),
                    unit=ing.get("unit"),
                    category=ing.get("category"),
                    sort_order=idx,
                )
            )
        s.add(r)
        s.commit()
        s.refresh(r)
        return r


def run(coro):
    return asyncio.run(coro)


# ─── list_recipes ─────────────────────────────────────────────────────────────

def test_list_recipes_empty(in_memory_db):
    from app.mcp_server import _dispatch
    result = json.loads(run(_dispatch("list_recipes", {})))
    assert result == []


def test_list_recipes_returns_accepted(in_memory_db):
    _add_recipe(in_memory_db, title="Soup")
    from app.mcp_server import _dispatch
    result = json.loads(run(_dispatch("list_recipes", {})))
    assert len(result) == 1
    assert result[0]["title"] == "Soup"


def test_list_recipes_filter_course(in_memory_db):
    _add_recipe(in_memory_db, title="Salad", course="salad")
    _add_recipe(in_memory_db, title="Steak", course="main")
    from app.mcp_server import _dispatch
    result = json.loads(run(_dispatch("list_recipes", {"course": "salad"})))
    assert len(result) == 1
    assert result[0]["title"] == "Salad"


def test_list_recipes_filter_vegetarian(in_memory_db):
    _add_recipe(in_memory_db, title="Veggie Curry", is_vegetarian=True)
    _add_recipe(in_memory_db, title="Beef Stew", is_vegetarian=False)
    from app.mcp_server import _dispatch
    result = json.loads(run(_dispatch("list_recipes", {"is_vegetarian": True})))
    assert len(result) == 1
    assert result[0]["title"] == "Veggie Curry"


def test_list_recipes_filter_favourite(in_memory_db):
    _add_recipe(in_memory_db, title="Fav", is_favourite=True)
    _add_recipe(in_memory_db, title="Meh", is_favourite=False)
    from app.mcp_server import _dispatch
    result = json.loads(run(_dispatch("list_recipes", {"is_favourite": True})))
    assert len(result) == 1
    assert result[0]["title"] == "Fav"


# ─── get_recipe ───────────────────────────────────────────────────────────────

def test_get_recipe_found(in_memory_db):
    r = _add_recipe(
        in_memory_db,
        title="Risotto",
        ingredients=[{"name": "Rice", "quantity_per_person": 80, "unit": "g", "category": "pantry"}],
    )
    from app.mcp_server import _dispatch
    result = json.loads(run(_dispatch("get_recipe", {"recipe_id": r.id})))
    assert result["title"] == "Risotto"
    assert len(result["ingredients"]) == 1
    assert result["ingredients"][0]["name"] == "Rice"


def test_get_recipe_not_found(in_memory_db):
    from app.mcp_server import _dispatch
    result = json.loads(run(_dispatch("get_recipe", {"recipe_id": 999})))
    assert "error" in result


# ─── create_recipe ────────────────────────────────────────────────────────────

def test_create_recipe_minimal(in_memory_db):
    from app.mcp_server import _dispatch
    result = json.loads(run(_dispatch("create_recipe", {"title": "New Recipe"})))
    assert result["title"] == "New Recipe"
    assert result["id"] is not None


def test_create_recipe_with_ingredients_and_steps(in_memory_db):
    from app.mcp_server import _dispatch
    result = json.loads(run(_dispatch("create_recipe", {
        "title": "Omelette",
        "course": "breakfast",
        "is_vegetarian": True,
        "ingredients": [
            {"name": "Eggs", "quantity_per_person": 2, "unit": "pcs", "category": "dairy"},
            {"name": "Butter", "quantity_per_person": 10, "unit": "g", "category": "dairy"},
        ],
        "steps": ["Beat eggs.", "Melt butter.", "Pour eggs into pan."],
    })))
    assert result["course"] == "breakfast"
    assert result["is_vegetarian"] is True
    assert len(result["ingredients"]) == 2
    assert len(result["steps"]) == 3


def test_create_recipe_appears_in_list(in_memory_db):
    from app.mcp_server import _dispatch
    run(_dispatch("create_recipe", {"title": "Pancakes"}))
    result = json.loads(run(_dispatch("list_recipes", {})))
    assert any(r["title"] == "Pancakes" for r in result)


# ─── list_plans / create_plan / get_plan ──────────────────────────────────────

def test_list_plans_empty(in_memory_db):
    from app.mcp_server import _dispatch
    result = json.loads(run(_dispatch("list_plans", {})))
    assert result == []


def test_create_and_get_plan(in_memory_db):
    from app.mcp_server import _dispatch
    created = json.loads(run(_dispatch("create_plan", {"name": "Week 1"})))
    assert created["name"] == "Week 1"
    assert created["id"] is not None

    fetched = json.loads(run(_dispatch("get_plan", {"plan_id": created["id"]})))
    assert fetched["name"] == "Week 1"
    assert fetched["entries"] == []


def test_create_plan_with_entries(in_memory_db):
    r = _add_recipe(in_memory_db, title="Pasta")
    from app.mcp_server import _dispatch
    plan = json.loads(run(_dispatch("create_plan", {
        "name": "Week 2",
        "entries": [{"recipe_id": r.id, "day": "Monday", "meal": "Dinner", "people": 3}],
    })))
    assert len(plan["entries"]) == 1
    assert plan["entries"][0]["slot"] == "Monday-Dinner"
    assert plan["entries"][0]["people"] == 3


def test_get_plan_not_found(in_memory_db):
    from app.mcp_server import _dispatch
    result = json.loads(run(_dispatch("get_plan", {"plan_id": 999})))
    assert "error" in result


# ─── update_plan ──────────────────────────────────────────────────────────────

def test_update_plan_name(in_memory_db):
    from app.mcp_server import _dispatch
    plan = json.loads(run(_dispatch("create_plan", {"name": "Old Name"})))
    updated = json.loads(run(_dispatch("update_plan", {"plan_id": plan["id"], "name": "New Name"})))
    assert updated["name"] == "New Name"


def test_update_plan_entries_replaces_all(in_memory_db):
    r1 = _add_recipe(in_memory_db, title="Pizza")
    r2 = _add_recipe(in_memory_db, title="Salad")
    from app.mcp_server import _dispatch
    plan = json.loads(run(_dispatch("create_plan", {
        "name": "Week",
        "entries": [{"recipe_id": r1.id, "day": "Monday", "meal": "Dinner"}],
    })))
    updated = json.loads(run(_dispatch("update_plan", {
        "plan_id": plan["id"],
        "entries": [
            {"recipe_id": r2.id, "day": "Tuesday", "meal": "Lunch"},
            {"recipe_id": r1.id, "day": "Wednesday", "meal": "Dinner"},
        ],
    })))
    assert len(updated["entries"]) == 2
    slots = {e["slot"] for e in updated["entries"]}
    assert slots == {"Tuesday-Lunch", "Wednesday-Dinner"}


def test_update_plan_not_found(in_memory_db):
    from app.mcp_server import _dispatch
    result = json.loads(run(_dispatch("update_plan", {"plan_id": 999})))
    assert "error" in result


# ─── get_shopping_list ────────────────────────────────────────────────────────

def test_get_shopping_list_aggregates_ingredients(in_memory_db):
    r = _add_recipe(
        in_memory_db,
        title="Soup",
        ingredients=[
            {"name": "Carrots", "quantity_per_person": 100, "unit": "g", "category": "produce"},
            {"name": "Onion", "quantity_per_person": 50, "unit": "g", "category": "produce"},
        ],
    )
    from app.mcp_server import _dispatch
    plan = json.loads(run(_dispatch("create_plan", {
        "name": "Week",
        "entries": [{"recipe_id": r.id, "day": "Monday", "meal": "Dinner", "people": 2}],
    })))
    sl = json.loads(run(_dispatch("get_shopping_list", {"plan_id": plan["id"]})))
    categories = {c["category"]: c["items"] for c in sl["categories"]}
    assert "produce" in categories
    names = {i["name"] for i in categories["produce"]}
    assert "Carrots" in names
    assert "Onion" in names
    carrot = next(i for i in categories["produce"] if i["name"] == "Carrots")
    assert carrot["quantity"] == 200  # 100 g/person × 2 people


def test_get_shopping_list_not_found(in_memory_db):
    from app.mcp_server import _dispatch
    result = json.loads(run(_dispatch("get_shopping_list", {"plan_id": 999})))
    assert "error" in result


# ─── unknown tool ─────────────────────────────────────────────────────────────

def test_unknown_tool_returns_error(in_memory_db):
    from app.mcp_server import _dispatch
    result = json.loads(run(_dispatch("nonexistent_tool", {})))
    assert "error" in result
