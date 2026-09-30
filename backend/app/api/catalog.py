from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services import catalog as catalog_service

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/skills")
def skills():
    return {"items": catalog_service.list_skills()}


@router.get("/experts")
def experts():
    return {"items": catalog_service.list_experts()}


@router.get("/scenes")
def scenes():
    return {"items": [catalog_service.public_scene(s) for s in catalog_service.list_scenes()]}


class DetectBody(BaseModel):
    prompt: str = Field(default="", max_length=8000)


@router.post("/scenes/detect")
def detect_scene(body: DetectBody):
    return catalog_service.detect_scene(body.prompt)
