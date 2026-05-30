from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session

from app import models
from app.db import get_session
from app.services import recipe_service

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.get("/", response_model=list[models.RecipeSummary])
def list_recipes(
    status: str = "accepted",
    session: Session = Depends(get_session),
):
    return recipe_service.list_recipes(session, status=status)


@router.get("/{recipe_id}", response_model=models.RecipeRead)
def get_recipe(recipe_id: int, session: Session = Depends(get_session)):
    read = recipe_service.get_recipe(session, recipe_id)
    if read is None:
        raise HTTPException(404, "Recipe not found")
    return read


@router.put("/{recipe_id}", response_model=models.RecipeRead)
def update_recipe(
    recipe_id: int,
    data: models.RecipeUpdate,
    session: Session = Depends(get_session),
):
    read = recipe_service.update_recipe(session, recipe_id, data)
    if read is None:
        raise HTTPException(404, "Recipe not found")
    return read


@router.delete("/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: int, session: Session = Depends(get_session)):
    if not recipe_service.delete_recipe(session, recipe_id):
        raise HTTPException(404, "Recipe not found")


@router.get("/{recipe_id}/source")
def get_source(recipe_id: int, session: Session = Depends(get_session)):
    from sqlmodel import Session as _S
    recipe = session.get(models.Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(404, "Recipe not found")
    path = recipe_service.get_source_path(recipe)
    if path is None or not path.exists():
        raise HTTPException(404, "Source file not available")
    media_types = {"pdf": "application/pdf", "epub": "application/epub+zip"}
    media_type = media_types.get(recipe.source_format or "", "application/octet-stream")
    return FileResponse(str(path), media_type=media_type, filename=recipe.source_file)
