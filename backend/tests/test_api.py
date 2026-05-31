"""Integration tests for /recipes and /plans endpoints using a temp SQLite DB."""
import os
import tempfile
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app import models
from app.db import get_session


@pytest.fixture(scope="function")
def client() -> Generator[TestClient, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["DATA_DIR"] = tmpdir
        # fresh in-memory DB per test
        eng = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(eng)

        def override_session():
            with Session(eng) as s:
                yield s

        from app.main import app
        app.dependency_overrides[get_session] = override_session

        with TestClient(app) as c:
            yield c

        app.dependency_overrides.clear()


# ─── recipes ─────────────────────────────────────────────────────────────────

def _seed_recipe(client: TestClient, **kwargs) -> dict:
    """Insert an accepted recipe directly through the DB override."""
    from app.main import app
    from app.db import get_session as real_gs
    session_dep = app.dependency_overrides.get(real_gs) or real_gs
    with next(session_dep()) as session:
        r = models.Recipe(
            title=kwargs.get("title", "Test Recipe"),
            base_servings=kwargs.get("base_servings", 4),
            status=models.RECIPE_ACCEPTED,
        )
        session.add(r)
        session.commit()
        session.refresh(r)
        for idx, (name, qty, unit, cat) in enumerate(kwargs.get("ingredients", [])):
            session.add(models.Ingredient(
                recipe_id=r.id, name=name,
                quantity_per_person=qty, unit=unit, category=cat,
                sort_order=idx,
            ))
        for idx, text in enumerate(kwargs.get("steps", [])):
            session.add(models.InstructionStep(recipe_id=r.id, step_number=idx+1, text=text))
        session.commit()
        return {"id": r.id, "title": r.title}


def test_list_recipes_empty(client):
    r = client.get("/api/recipes/")
    assert r.status_code == 200
    assert r.json() == []


def test_get_recipe_not_found(client):
    assert client.get("/api/recipes/999").status_code == 404


def test_list_and_get_recipe(client):
    _seed_recipe(client, title="Pasta", base_servings=2,
                 ingredients=[("Flour", 100.0, "g", "pantry")],
                 steps=["Boil water", "Cook pasta"])
    items = client.get("/api/recipes/").json()
    assert len(items) == 1
    assert items[0]["title"] == "Pasta"

    detail = client.get(f"/api/recipes/{items[0]['id']}").json()
    assert detail["title"] == "Pasta"
    assert detail["base_servings"] == 2
    assert len(detail["ingredients"]) == 1
    assert detail["ingredients"][0]["quantity_per_person"] == 100.0
    assert detail["ingredients"][0]["unit"] == "g"
    assert detail["steps"][0]["text"] == "Boil water"


def test_update_recipe_title(client):
    info = _seed_recipe(client, title="Old Name")
    r = client.put(f"/api/recipes/{info['id']}", json={"title": "New Name"})
    assert r.status_code == 200
    assert r.json()["title"] == "New Name"


def test_update_recipe_ingredients_replaces_all(client):
    info = _seed_recipe(client, title="R",
                        ingredients=[("Egg", 1.0, "pcs", "dairy"), ("Milk", 50.0, "ml", "dairy")])
    r = client.put(f"/api/recipes/{info['id']}", json={
        "ingredients": [{"name": "Butter", "quantity_per_person": 25.0, "unit": "g", "category": "dairy"}]
    })
    assert r.status_code == 200
    ings = r.json()["ingredients"]
    assert len(ings) == 1
    assert ings[0]["name"] == "Butter"


def test_delete_recipe(client):
    info = _seed_recipe(client, title="ToDelete")
    assert client.delete(f"/api/recipes/{info['id']}").status_code == 204
    assert client.get(f"/api/recipes/{info['id']}").status_code == 404


# ─── plans ───────────────────────────────────────────────────────────────────

def test_create_and_list_plan(client):
    r = client.post("/api/plans/", json={"name": "Week 1"})
    assert r.status_code == 201
    plan = r.json()
    assert plan["name"] == "Week 1"
    assert plan["entries"] == []

    plans = client.get("/api/plans/").json()
    assert len(plans) == 1
    assert plans[0]["entry_count"] == 0


def test_update_plan_adds_entries(client):
    recipe = _seed_recipe(client, title="Soup",
                          ingredients=[("Onion", 0.5, "pcs", "produce"),
                                       ("Carrot", 50.0, "g", "produce")])
    plan_id = client.post("/api/plans/", json={"name": "Plan A"}).json()["id"]

    r = client.put(f"/api/plans/{plan_id}", json={
        "entries": [{"recipe_id": recipe["id"], "slot": "Mon-dinner", "people": 4}]
    })
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["slot"] == "Mon-dinner"
    assert entries[0]["people"] == 4


def test_shopping_list_scales_and_aggregates(client):
    recipe = _seed_recipe(
        client, title="Salad",
        ingredients=[
            ("Tomato", 1.0, "pcs", "produce"),
            ("Lettuce", 50.0, "g", "produce"),
        ],
    )
    plan_id = client.post("/api/plans/", json={"name": "P"}).json()["id"]
    client.put(f"/api/plans/{plan_id}", json={
        "entries": [{"recipe_id": recipe["id"], "slot": "Tue-lunch", "people": 3}]
    })

    sl = client.get(f"/api/plans/{plan_id}/shopping-list").json()
    items = {i["name"]: i for c in sl["categories"] for i in c["items"]}

    assert items["Tomato"]["quantity"] == 3.0   # 1/person * 3
    assert items["Lettuce"]["quantity"] == 150.0  # 50g/person * 3


def test_delete_plan(client):
    plan_id = client.post("/api/plans/", json={"name": "Temp"}).json()["id"]
    assert client.delete(f"/api/plans/{plan_id}").status_code == 204
    assert client.get(f"/api/plans/{plan_id}").status_code == 404
