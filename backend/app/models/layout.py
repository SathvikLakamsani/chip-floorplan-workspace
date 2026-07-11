"""Pydantic models for chip floorplan layout data."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class BlockType(str, Enum):
    COMPUTE = "compute"
    SRAM = "sram"
    NOC = "noc"
    IO = "io"
    PLL = "pll"
    CONTROLLER = "controller"
    OTHER = "other"


class ConstraintPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Chip(BaseModel):
    name: str
    width: float
    height: float
    unit: str = "microns"


class Block(BaseModel):
    id: str
    name: str
    type: BlockType | str
    x: float
    y: float
    width: float
    height: float
    fixed: bool = False
    power: float = 0.0
    clock_domain: str = ""
    voltage_domain: str = ""
    criticality: float = Field(default=0.5, ge=0.0, le=1.0)


class Net(BaseModel):
    id: str
    source: str
    sinks: list[str]
    width: int = 32
    criticality: float = Field(default=0.5, ge=0.0, le=1.0)
    traffic: float = Field(default=0.5, ge=0.0, le=1.0)


class Constraint(BaseModel):
    id: str
    type: str
    description: str
    targets: list[str]
    priority: ConstraintPriority | str = ConstraintPriority.MEDIUM


class Metrics(BaseModel):
    wns: float = 0.0
    tns: float = 0.0
    wire_length: float = 0.0
    congestion_score: float = Field(default=0.0, ge=0.0, le=1.0)
    area_utilization: float = Field(default=0.0, ge=0.0, le=1.0)
    power_estimate: float = 0.0


class Layout(BaseModel):
    chip: Chip
    blocks: list[Block]
    nets: list[Net]
    constraints: list[Constraint] = Field(default_factory=list)
    metrics: Metrics | None = None


class ActionType(str, Enum):
    MOVE_BLOCKS = "move_blocks"
    LOCK_BLOCKS = "lock_blocks"
    RESIZE_BLOCKS = "resize_blocks"
    UPDATE_PROPERTY = "update_property"
    GENERATE_CANDIDATES = "generate_candidates"
    ADD_CONSTRAINT = "add_constraint"


class CommandAction(BaseModel):
    type: ActionType | str
    targets: list[str] = Field(default_factory=list)
    reason: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class CommandRequest(BaseModel):
    command: str
    layout: Layout


class CommandResponse(BaseModel):
    actions: list[CommandAction]
    preview_layout: Layout | None = None
    expected_metric_delta: dict[str, float] = Field(default_factory=dict)
    explanation: str = ""
    # How the command was interpreted: "rule", "llm", or "none".
    source: str = "rule"


class ApplyActionsRequest(BaseModel):
    layout: Layout
    actions: list[CommandAction]


class AnalyzeResponse(BaseModel):
    layout: Layout
    metrics: Metrics
    explanations: list[str] = Field(default_factory=list)


class CandidateLayout(BaseModel):
    id: str
    name: str
    layout: Layout
    explanation: str
    metric_deltas: dict[str, float] = Field(default_factory=dict)


class GenerateCandidatesResponse(BaseModel):
    baseline: Layout
    candidates: list[CandidateLayout]


class ExportRequest(BaseModel):
    layout: Layout
    format: Literal["json", "tcl", "def"] = "json"


class ExportResponse(BaseModel):
    format: str
    content: str
    filename: str
