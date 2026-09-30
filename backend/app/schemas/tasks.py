from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PlanStepOut(BaseModel):
    name: str
    goal: str = ""
    tool_hint: str = ""


class PlanOut(BaseModel):
    title: str = ""
    steps: list[PlanStepOut] = Field(default_factory=list)
    cost_factors: dict[str, Any] = Field(default_factory=dict)


class TaskCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    urls: list[str] = Field(default_factory=list, max_length=3)
    skill_id: str | None = None
    expert_id: str | None = None


class TaskConfirm(BaseModel):
    confirm_cost: bool = False


class TaskReplan(BaseModel):
    prompt: str | None = Field(default=None, max_length=8000)
    urls: list[str] | None = Field(default=None, max_length=3)


class TaskRewrite(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)


class TaskMerge(BaseModel):
    task_ids: list[str] = Field(min_length=2, max_length=20)


class StepOut(BaseModel):
    seq: int
    name: str
    status: str
    detail: dict[str, Any] = Field(default_factory=dict)


class UploadOut(BaseModel):
    id: int
    filename: str
    size_bytes: int
    text_excerpt: str = ""


class TaskOut(BaseModel):
    id: str
    title: str
    user_prompt: str
    status: str
    cost_estimate_cny: float
    cost_confirmed: bool
    skill_id: str | None = None
    expert_id: str | None = None
    plan: PlanOut | None = None
    steps: list[StepOut] = Field(default_factory=list)
    uploads: list[UploadOut] = Field(default_factory=list)
    report_path: str | None = None
    has_report: bool = False
    merged_into_id: str | None = None
    merged_from_ids: list[str] = Field(default_factory=list)
    search_snippet: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class TaskListOut(BaseModel):
    items: list[TaskOut]
