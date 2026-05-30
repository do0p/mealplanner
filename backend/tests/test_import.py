"""Import pipeline tests — use FakeRecipeExtractor so no Ollama needed."""
import io
import os
import tempfile
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.adapters.extractor_registry import ExtractorRegistry
from app.adapters.fake_extractor import FakeRecipeExtractor
from app.adapters.pdf_extractor import PdfTextExtractor
from app.db import get_session
from app.dependencies import get_import_service
from app.ports.recipe_extractor import ExtractedIngredient, ExtractedRecipe
from app.services.import_service import ImportService


def _make_client(fake_recipes=None, tmp_dir=None) -> tuple[TestClient, any]:
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)

    def session_factory():
        return Session(eng)

    registry = ExtractorRegistry()
    registry.register(PdfTextExtractor())
    extractor = FakeRecipeExtractor(fake_recipes)
    svc = ImportService(session_factory=session_factory, text_registry=registry, recipe_extractor=extractor)

    from app.main import app
    app.dependency_overrides[get_session] = lambda: session_factory()
    app.dependency_overrides[get_import_service] = lambda: svc

    os.environ["DATA_DIR"] = tmp_dir or tempfile.mkdtemp()
    return TestClient(app), svc


def _make_pdf(text: str = "Recipe content here") -> bytes:
    """Generate a minimal valid PDF with one page of text."""
    import pypdf
    from io import BytesIO
    buf = BytesIO()
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    writer.write(buf)
    return buf.getvalue()


_PDF_BYTES = _make_pdf()


@pytest.fixture
def tmp(tmp_path):
    return str(tmp_path)


@pytest.fixture(autouse=True)
def cleanup():
    yield
    from app.main import app
    app.dependency_overrides.clear()


def test_upload_creates_pending_job(tmp):
    client, _ = _make_client(tmp_dir=tmp)
    r = client.post("/imports/uploads", files={"file": ("test.pdf", _PDF_BYTES, "application/pdf")})
    assert r.status_code == 201
    job = r.json()
    assert job["status"] == "pending"
    assert job["filename"] == "test.pdf"
    assert job["source_format"] == "pdf"


def test_upload_unsupported_format_returns_415(tmp):
    client, _ = _make_client(tmp_dir=tmp)
    r = client.post("/imports/uploads", files={"file": ("doc.epub", b"PK\x03\x04", "application/epub")})
    assert r.status_code == 415


def test_list_jobs_empty(tmp):
    client, _ = _make_client(tmp_dir=tmp)
    assert client.get("/imports/").json() == []


def test_process_creates_draft_recipes(tmp):
    client, svc = _make_client(tmp_dir=tmp)
    upload = client.post("/imports/uploads", files={"file": ("r.pdf", _PDF_BYTES, "application/pdf")})
    job_id = upload.json()["id"]

    # simulate processing synchronously (fake extractor, no background needed)
    svc.process_job(job_id)

    job = client.get(f"/imports/{job_id}").json()
    assert job["status"] == "completed"
    assert job["recipe_count"] == 1
    assert len(job["recipes"]) == 1
    assert job["recipes"][0]["title"] == "Test Recipe"
    assert job["recipes"][0]["status"] == "draft"


def test_ingredients_stored_per_person(tmp):
    recipes = [
        ExtractedRecipe(
            title="Cake",
            base_servings=4,
            ingredients=[ExtractedIngredient(name="Flour", quantity=400.0, unit="g", category="pantry")],
            steps=["Mix and bake."],
        )
    ]
    client, svc = _make_client(fake_recipes=recipes, tmp_dir=tmp)
    client.post("/imports/uploads", files={"file": ("cake.pdf", _PDF_BYTES, "application/pdf")})
    jobs = client.get("/imports/").json()
    svc.process_job(jobs[0]["id"])

    job = client.get(f"/imports/{jobs[0]['id']}").json()
    recipe_id = job["recipes"][0]["id"]
    detail = client.get(f"/recipes/{recipe_id}?status=all").json()

    flour = detail["ingredients"][0]
    assert flour["name"] == "Flour"
    assert flour["quantity_per_person"] == 100.0  # 400g / 4 servings
    assert flour["unit"] == "g"


def test_imperial_converted_at_import(tmp):
    recipes = [
        ExtractedRecipe(
            title="Bread",
            base_servings=2,
            ingredients=[ExtractedIngredient(name="Milk", quantity=1.0, unit="cup", category="dairy")],
            steps=["Pour milk."],
        )
    ]
    client, svc = _make_client(fake_recipes=recipes, tmp_dir=tmp)
    client.post("/imports/uploads", files={"file": ("b.pdf", _PDF_BYTES, "application/pdf")})
    jobs = client.get("/imports/").json()
    svc.process_job(jobs[0]["id"])
    job = client.get(f"/imports/{jobs[0]['id']}").json()
    recipe_id = job["recipes"][0]["id"]
    detail = client.get(f"/recipes/{recipe_id}?status=all").json()

    milk = detail["ingredients"][0]
    assert milk["unit"] == "cup"
    assert milk["quantity_per_person"] == 0.5  # 1 cup / 2 servings


def test_accept_all_marks_recipes_accepted(tmp):
    client, svc = _make_client(tmp_dir=tmp)
    client.post("/imports/uploads", files={"file": ("r.pdf", _PDF_BYTES, "application/pdf")})
    jobs = client.get("/imports/").json()
    job_id = jobs[0]["id"]
    svc.process_job(job_id)

    r = client.post(f"/imports/{job_id}/accept")
    assert r.status_code == 200
    assert r.json()["accepted"] == 1

    job = client.get(f"/imports/{job_id}").json()
    assert job["recipes"][0]["status"] == "accepted"


def test_accept_specific_recipe_ids(tmp):
    two_recipes = [
        ExtractedRecipe(title="R1", base_servings=2, ingredients=[], steps=["Step 1."]),
        ExtractedRecipe(title="R2", base_servings=2, ingredients=[], steps=["Step 2."]),
    ]
    client, svc = _make_client(fake_recipes=two_recipes, tmp_dir=tmp)
    client.post("/imports/uploads", files={"file": ("r.pdf", _PDF_BYTES, "application/pdf")})
    jobs = client.get("/imports/").json()
    job_id = jobs[0]["id"]
    svc.process_job(job_id)

    all_recipes = client.get(f"/imports/{job_id}").json()["recipes"]
    first_id = all_recipes[0]["id"]

    client.post(f"/imports/{job_id}/accept", json={"recipe_ids": [first_id]})
    # only R1 accepted, R2 still draft
    accepted = client.get("/recipes/?status=accepted").json()
    assert len(accepted) == 1
    drafts = client.get("/recipes/?status=draft").json()
    assert len(drafts) == 1


def test_llm_status_fake_extractor_available(tmp):
    client, _ = _make_client(tmp_dir=tmp)
    r = client.get("/imports/llm-status")
    assert r.status_code == 200
    assert r.json()["available"] is True
