"""Pydantic models for chip floorplan layout data.

The schema models real backend physical-design concepts: die/core areas,
hard macros vs. soft logic, orientation, placement status, halos/keepouts,
pins, richer nets, constraints, timing paths, congestion/power regions and an
extended QoR metric set. All physical-design fields are optional with sensible
defaults so older/simpler layouts (and partial OpenROAD imports) still validate.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class BlockType(str, Enum):
    COMPUTE = "compute"
    SRAM = "sram"
    MEMORY = "memory"
    NOC = "noc"
    IO = "io"
    PLL = "pll"
    CLOCK = "clock"
    CONTROLLER = "controller"
    ANALOG = "analog"
    STDCELL = "stdcell"
    OTHER = "other"


class BlockClass(str, Enum):
    HARD_MACRO = "hard_macro"
    SOFT_LOGIC = "soft_logic"
    IO = "io"
    ANALOG = "analog"
    CLOCK = "clock"
    MEMORY = "memory"
    STANDARD_CELL_REGION = "standard_cell_region"


class Orientation(str, Enum):
    N = "N"
    S = "S"
    E = "E"
    W = "W"
    FN = "FN"
    FS = "FS"
    FE = "FE"
    FW = "FW"


class PlacementStatus(str, Enum):
    PLACED = "placed"
    FIXED = "fixed"
    UNPLACED = "unplaced"


class PinType(str, Enum):
    SIGNAL = "signal"
    CLOCK = "clock"
    POWER = "power"
    GROUND = "ground"


class PinSide(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"


class NetType(str, Enum):
    SIGNAL = "signal"
    CLOCK = "clock"
    POWER = "power"
    GROUND = "ground"


class ConstraintPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Rect(BaseModel):
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0


class Halo(BaseModel):
    left: float = 0.0
    right: float = 0.0
    top: float = 0.0
    bottom: float = 0.0


class Pin(BaseModel):
    name: str
    side: PinSide | str = PinSide.LEFT
    # Fractional position (0..1) along the chosen side.
    offset: float = Field(default=0.5, ge=0.0, le=1.0)
    type: PinType | str = PinType.SIGNAL
    direction: str = ""  # INPUT / OUTPUT / INOUT when known


class Chip(BaseModel):
    name: str
    unit: str = "microns"
    # Full die area and inner core area. width/height kept as convenience
    # mirrors of the die extent for backward compatibility.
    die: Rect | None = None
    core: Rect | None = None
    width: float = 0.0
    height: float = 0.0

    def model_post_init(self, __context: Any) -> None:  # noqa: D401
        # Backfill die/core/width/height so either representation works.
        if self.die is None:
            self.die = Rect(x=0, y=0, width=self.width, height=self.height)
        if self.width == 0.0:
            self.width = self.die.width
        if self.height == 0.0:
            self.height = self.die.height
        if self.core is None:
            # Default core = 8% inset from die.
            m = min(self.die.width, self.die.height) * 0.08
            self.core = Rect(
                x=self.die.x + m,
                y=self.die.y + m,
                width=max(0.0, self.die.width - 2 * m),
                height=max(0.0, self.die.height - 2 * m),
            )


class Block(BaseModel):
    id: str
    name: str
    type: BlockType | str
    cls: BlockClass | str = Field(default=BlockClass.SOFT_LOGIC, alias="class")
    x: float
    y: float
    width: float
    height: float
    fixed: bool = False
    orientation: Orientation | str = Orientation.N
    placement_status: PlacementStatus | str = PlacementStatus.PLACED
    power: float = 0.0
    clock_domain: str = ""
    voltage_domain: str = ""
    criticality: float = Field(default=0.5, ge=0.0, le=1.0)
    halo: Halo | None = None
    keepout: bool = False
    pins: list[Pin] = Field(default_factory=list)
    # For grouped standard cells: how many instances this region represents.
    instance_count: int = 0

    model_config = {"populate_by_name": True}

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def power_density(self) -> float:
        a = self.area
        return (self.power / a) if a > 0 else 0.0


class Net(BaseModel):
    id: str
    name: str = ""
    source: str
    sinks: list[str]
    width: int = 32
    criticality: float = Field(default=0.5, ge=0.0, le=1.0)
    traffic: float = Field(default=0.5, ge=0.0, le=1.0)
    type: NetType | str = NetType.SIGNAL

    def model_post_init(self, __context: Any) -> None:
        if not self.name:
            self.name = self.id


class Constraint(BaseModel):
    id: str
    type: str
    description: str
    targets: list[str]
    priority: ConstraintPriority | str = ConstraintPriority.MEDIUM
    params: dict[str, Any] = Field(default_factory=dict)


class TimingPath(BaseModel):
    id: str
    startpoint: str
    endpoint: str
    slack: float = 0.0
    distance: float = 0.0
    criticality: float = Field(default=0.5, ge=0.0, le=1.0)
    clock: str = ""
    explanation: str = ""


class CongestionRegion(BaseModel):
    x: float
    y: float
    width: float
    height: float
    score: float = Field(default=0.5, ge=0.0, le=1.0)
    reason: str = ""


class PowerRegion(BaseModel):
    x: float
    y: float
    width: float
    height: float
    density: float = Field(default=0.5, ge=0.0, le=1.0)
    reason: str = ""


class Metrics(BaseModel):
    wns: float = 0.0
    tns: float = 0.0
    violating_paths: int = 0
    wire_length: float = 0.0
    congestion_score: float = Field(default=0.0, ge=0.0, le=1.0)
    area_utilization: float = Field(default=0.0, ge=0.0, le=1.0)
    power_estimate: float = 0.0
    drc_count: int = 0


class Layout(BaseModel):
    chip: Chip
    blocks: list[Block]
    nets: list[Net] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    timing_paths: list[TimingPath] = Field(default_factory=list)
    congestion_regions: list[CongestionRegion] = Field(default_factory=list)
    power_regions: list[PowerRegion] = Field(default_factory=list)
    metrics: Metrics | None = None

    model_config = {"populate_by_name": True}


# --------------------------------------------------------------------------
# DRC / legality
# --------------------------------------------------------------------------
class DRCViolation(BaseModel):
    id: str
    severity: Severity | str = Severity.WARNING
    rule: str
    message: str
    targets: list[str] = Field(default_factory=list)
    region: Rect | None = None
    suggestion: str = ""


class DRCReport(BaseModel):
    violations: list[DRCViolation] = Field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(
            1
            for v in self.violations
            if (v.severity if isinstance(v.severity, str) else v.severity.value)
            == Severity.ERROR.value
        )


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------
class ActionType(str, Enum):
    MOVE_BLOCKS = "move_blocks"
    LOCK_BLOCKS = "lock_blocks"
    UNLOCK_BLOCKS = "unlock_blocks"
    RESIZE_BLOCKS = "resize_blocks"
    UPDATE_PROPERTY = "update_property"
    ADD_KEEPOUT = "add_keepout"
    ADD_CONSTRAINT = "add_constraint"
    GENERATE_CANDIDATES = "generate_candidates"
    SET_OVERLAY = "set_overlay"
    EXPLAIN = "explain"
    # Structural edits — create/remove/duplicate design objects.
    ADD_BLOCK = "add_block"
    REMOVE_BLOCK = "remove_block"
    CLONE_BLOCK = "clone_block"
    ADD_NET = "add_net"
    REMOVE_NET = "remove_net"
    ALIGN_BLOCKS = "align_blocks"
    DISTRIBUTE_BLOCKS = "distribute_blocks"
    SET_CHIP = "set_chip"


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
    # UI-only overlay toggles requested (e.g. {"congestion": true}).
    overlays: dict[str, bool] = Field(default_factory=dict)
    # How the command was interpreted: "rule", "llm", or "none".
    source: str = "rule"


class ApplyActionsRequest(BaseModel):
    layout: Layout
    actions: list[CommandAction]


class AnalyzeResponse(BaseModel):
    layout: Layout
    metrics: Metrics
    explanations: list[str] = Field(default_factory=list)
    drc: DRCReport = Field(default_factory=DRCReport)


class CandidateLayout(BaseModel):
    id: str
    name: str
    objective: str = "balanced"
    layout: Layout
    explanation: str
    tradeoff: str = ""
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


# --------------------------------------------------------------------------
# OpenROAD / OpenLane offline import
# --------------------------------------------------------------------------
class ImportRequest(BaseModel):
    path: str


class ImportResponse(BaseModel):
    layout: Layout | None = None
    warnings: list[str] = Field(default_factory=list)
    files_found: dict[str, list[str]] = Field(default_factory=dict)
    design_name: str = ""
    unit_scale: str = ""
