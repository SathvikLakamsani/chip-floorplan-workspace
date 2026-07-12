"""FastAPI application for AI-assisted chip floorplanning."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.mock_eda import MockEDAAdapter
from app.models.layout import (
    AnalyzeResponse,
    ApplyActionsRequest,
    CandidateLayout,
    CommandRequest,
    CommandResponse,
    ExportRequest,
    ExportResponse,
    GenerateCandidatesResponse,
    Layout,
)
from app.services.analysis_engine import AnalysisEngine
from app.services.command_parser import CommandParser
from app.services.layout_operations import LayoutOperations

# Allow overriding the examples directory (e.g. in Docker) via env var.
EXAMPLES_DIR = Path(
    os.environ.get("EXAMPLES_DIR", Path(__file__).resolve().parents[1] / "examples")
)

DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://chip-floorplan-workspace.vercel.app",
    "https://chip-floorplan-workspace-chreate.vercel.app",
    "https://chip-floorplan-workspace-sathviklakamsani1-1534-chreate.vercel.app",
]

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "FRONTEND_ORIGINS", ",".join(DEFAULT_ALLOWED_ORIGINS)
    ).split(",")
    if origin.strip()
]

app = FastAPI(
    title="Chip Floorplan Workspace API",
    description="AI-assisted backend chip floorplanning workspace",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://chip-floorplan-workspace-[a-z0-9-]+-chreate\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_engine = AnalysisEngine()
_parser = CommandParser()
_ops = LayoutOperations()
_eda = MockEDAAdapter()


def _load_example_layout() -> Layout:
    path = EXAMPLES_DIR / "toy_ai_accelerator.json"
    data = json.loads(path.read_text())
    layout = Layout.model_validate(data)
    if layout.metrics is None:
        layout.metrics = _engine.analyze(layout)
    return layout


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/layouts/example", response_model=Layout)
def get_example_layout() -> Layout:
    return _load_example_layout()


@app.post("/api/layouts/analyze", response_model=AnalyzeResponse)
def analyze_layout(layout: Layout) -> AnalyzeResponse:
    metrics = _engine.analyze(layout)
    layout.metrics = metrics
    explanations = _engine.explain(layout, metrics)
    return AnalyzeResponse(layout=layout, metrics=metrics, explanations=explanations)


@app.post("/api/layouts/command", response_model=CommandResponse)
def parse_command(request: CommandRequest) -> CommandResponse:
    return _parser.parse(request)


@app.post("/api/layouts/apply", response_model=Layout)
def apply_actions(request: ApplyActionsRequest) -> Layout:
    return _ops.apply_actions(request.layout, request.actions)


@app.post("/api/layouts/generate-candidates", response_model=GenerateCandidatesResponse)
def generate_candidates(layout: Layout) -> GenerateCandidatesResponse:
    baseline_metrics = _engine.analyze(layout)
    layout.metrics = baseline_metrics
    raw_candidates = _ops.generate_candidates(layout, count=3)

    candidates: list[CandidateLayout] = []
    names = ["Candidate A", "Candidate B", "Candidate C"]
    for i, (candidate_layout, explanation) in enumerate(raw_candidates):
        cm = candidate_layout.metrics or _engine.analyze(candidate_layout)
        deltas = {
            "wns": round(cm.wns - baseline_metrics.wns, 3),
            "tns": round(cm.tns - baseline_metrics.tns, 3),
            "wire_length": round(cm.wire_length - baseline_metrics.wire_length, 1),
            "congestion_score": round(cm.congestion_score - baseline_metrics.congestion_score, 3),
            "area_utilization": round(cm.area_utilization - baseline_metrics.area_utilization, 3),
            "power_estimate": round(cm.power_estimate - baseline_metrics.power_estimate, 2),
        }
        candidates.append(
            CandidateLayout(
                id=f"candidate_{chr(97 + i)}",
                name=names[i] if i < len(names) else f"Candidate {i + 1}",
                layout=candidate_layout,
                explanation=explanation,
                metric_deltas=deltas,
            )
        )

    return GenerateCandidatesResponse(baseline=layout, candidates=candidates)


@app.post("/api/layouts/export", response_model=ExportResponse)
def export_layout(request: ExportRequest) -> ExportResponse:
    if request.format == "json":
        content = request.layout.model_dump_json(indent=2)
        filename = f"{request.layout.chip.name}_layout.json"
    elif request.format == "tcl":
        content = _eda.export_constraints(request.layout)
        filename = f"{request.layout.chip.name}_constraints.tcl"
        # TODO: Full Tcl constraint export for OpenROAD
    else:
        content = "# DEF export not yet implemented\n# TODO: DEF parser/writer"
        filename = f"{request.layout.chip.name}_floorplan.def"
        # TODO: DEF export

    return ExportResponse(format=request.format, content=content, filename=filename)
