from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ReportSection(BaseModel):
    id: str
    title: str


class ReportDocument(BaseModel):
    markdown: str
    version: int
    sections: list[ReportSection]


class ReportVersionInfo(BaseModel):
    version: int
    reason: str
    instruction: str
    created_at: datetime
    characters: int


class ReportVersionList(BaseModel):
    current_version: int
    items: list[ReportVersionInfo]


class ReportVersionPreview(ReportVersionInfo):
    markdown: str
    current_version: int
    diff: str
    diff_truncated: bool


class ReportRestore(BaseModel):
    version: int = Field(ge=1)
    expected_version: int = Field(ge=1)


class Metric(BaseModel):
    column: str
    index: int
    kind: str
    aggregation: Literal["sum", "mean"] = "sum"
    count: int
    missing_count: int
    invalid_count: int
    sum: float
    mean: float
    min: float
    max: float
    outlier_count: int


class GroupRow(BaseModel):
    label: str
    value: float
    count: int


class Group(BaseModel):
    dimension: str
    metric: str
    aggregation: Literal["sum", "mean"] = "sum"
    rows: list[GroupRow]


class Period(BaseModel):
    period: str
    metric: str
    aggregation: Literal["sum", "mean"] = "sum"
    value: float
    mom_pct: float | None
    yoy_pct: float | None


class DataIssue(BaseModel):
    row: int
    column: str
    kind: str
    value: str
    message: str


class DataChart(BaseModel):
    kind: Literal["bar", "line"]
    title: str
    labels: list[str]
    values: list[float]
    metric: str
    value_format: Literal["number", "percent"] = "number"


class TableSummary(BaseModel):
    id: str
    source: str
    sheet: str
    row_count: int
    column_count: int
    headers: list[str]
    metrics: list[Metric]
    groups: list[Group]
    periods: list[Period]
    date_column: str | None
    issues: list[DataIssue]
    issue_count: int
    warnings: list[str]
    charts: list[DataChart]


class DataSource(BaseModel):
    filename: str
    sha256: str


class AnalysisSummary(BaseModel):
    id: str
    complete: bool
    created_at: datetime
    source_count: int
    sheet_count: int
    row_count: int
    cell_count: int
    sources: list[DataSource]
    tables: list[TableSummary]


class AnalysisResponse(BaseModel):
    analysis: AnalysisSummary | None
