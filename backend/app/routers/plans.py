from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app import models
from app.db import get_session
from app.services import plan_service
from app.services.shopping_list import ShoppingList

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("/", response_model=list[models.PlanSummary])
def list_plans(session: Session = Depends(get_session)):
    return plan_service.list_plans(session)


@router.post("/", response_model=models.PlanRead, status_code=201)
def create_plan(data: models.PlanCreate, session: Session = Depends(get_session)):
    return plan_service.create_plan(session, data)


@router.get("/{plan_id}", response_model=models.PlanRead)
def get_plan(plan_id: int, session: Session = Depends(get_session)):
    plan = plan_service.get_plan(session, plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found")
    return plan


@router.put("/{plan_id}", response_model=models.PlanRead)
def update_plan(
    plan_id: int,
    data: models.PlanUpdate,
    session: Session = Depends(get_session),
):
    plan = plan_service.update_plan(session, plan_id, data)
    if plan is None:
        raise HTTPException(404, "Plan not found")
    return plan


@router.delete("/{plan_id}", status_code=204)
def delete_plan(plan_id: int, session: Session = Depends(get_session)):
    if not plan_service.delete_plan(session, plan_id):
        raise HTTPException(404, "Plan not found")


@router.get("/{plan_id}/shopping-list", response_model=ShoppingList)
def get_shopping_list(plan_id: int, session: Session = Depends(get_session)):
    sl = plan_service.get_shopping_list(session, plan_id)
    if sl is None:
        raise HTTPException(404, "Plan not found")
    return sl
