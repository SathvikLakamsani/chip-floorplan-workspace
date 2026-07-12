"""FastAPI application for AI-assisted chip floorplanning."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env before anything reads os.environ (e.g. the LLM parser).
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.eda.adapters import MockEDAAdapter, OpenROADImportAdapter
from app.models.layout import (
    AnalyzeResponse,
    ApplyActionsRequest,
    CandidateLayout,
    CommandRequest,
    CommandResponse,
    ExportRequest,
    ExportResponse,
    GenerateCandidatesResponse,
    ImportRequest,
    ImportResponse,
    Layout,
)
from app.services.analysis_engine import AnalysisEngine
from app.services.command_parser import CommandParser
from app.services.layout_operations import LayoutOperations
from app.services.validation import ValidationEngine

EXAMPLES_DIR = Path(
    os.environ.get("EXAMPLES_DIR", Path(__file__).resolve().parents[2] / "examples")
)

app = FastAPI(
    title="Chip Floorplan Workspace API",
    description="AI-assisted backend chip floorplanning workspace",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_engine = AnalysisEngine()
_parser = CommandParser()
_ops = LayoutOperations()
_validator = ValidationEngine()
_mock = MockEDAAdapter()
_openroad = OpenROADImportAdapter()


def _load_example_layout() -> Layout:
    path = EXAMPLES_DIR / "toy_ai_accelerator.json"
    data = json.loads(path.read_text())
    layout = Layout.model_validate(data)
    if layout.metrics is None:
        layout.metrics = _engine.analyze(layout)
    _engine.enrich(layout)
    return layout


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def get_config() -> dict[str, object]:
    return {
        "llm_enabled": _parser._llm.is_configured(),
        "llm_provider": _parser._llm.provider,
        "llm_model": _parser._llm.model if _parser._llm.is_configured() else None,
    }


@app.get("/api/layouts/example", response_model=Layout)
def get_example_layout() -> Layout:
    return _load_example_layout()


@app.post("/api/layouts/analyze", response_model=AnalyzeResponse)
def analyze_layout(layout: Layout) -> AnalyzeResponse:
    metrics = _engine.analyze(layout)
    layout.metrics = metrics
    _engine.enrich(layout)
    explanations = _engine.explain(layout, metrics)
    drc = _validator.check(layout, metrics)
    return AnalyzeResponse(
        layout=layout, metrics=metrics, explanations=explanations, drc=drc
    )


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
    _engine.enrich(layout)
    raw_candidates = _ops.generate_candidates(layout, count=3)

    names = {"timing": "Timing Optimized", "congestion": "Congestion Optimized", "compact": "Compact"}
    candidates: list[CandidateLayout] = []
    for i, (candidate_layout, objective, explanation, tradeoff) in enumerate(raw_candidates):
        cm = candidate_layout.metrics or _engine.analyze(candidate_layout)
        deltas = {
            "wns": round(cm.wns - baseline_metrics.wns, 3),
            "tns": round(cm.tns - baseline_metrics.tns, 3),
            "wire_length": round(cm.wire_length - baseline_metrics.wire_length, 1),
            "congestion_score": round(cm.congestion_score - baseline_metrics.congestion_score, 3),
            "area_utilization": round(cm.area_utilization - baseline_metrics.area_utilization, 3),
            "power_estimate": round(cm.power_estimate - baseline_metrics.power_estimate, 2),
            "drc_count": cm.drc_count - baseline_metrics.drc_count,
        }
        candidates.append(
            CandidateLayout(
                id=f"candidate_{chr(97 + i)}",
                name=names.get(objective, f"Candidate {chr(65 + i)}"),
                objective=objective,
                layout=candidate_layout,
                explanation=explanation,
                tradeoff=tradeoff,
                metric_deltas=deltas,
            )
        )

    return GenerateCandidatesResponse(baseline=layout, candidates=candidates)


@app.post("/api/import/openroad", response_model=ImportResponse)
def import_openroad(request: ImportRequest) -> ImportResponse:
    """Offline import of an existing OpenROAD/OpenLane run directory."""
    return _openroad.import_run(request.path)


@app.post("/api/layouts/export", response_model=ExportResponse)
def export_layout(request: ExportRequest) -> ExportResponse:
    name = request.layout.chip.name
    if request.format == "json":
        content = request.layout.model_dump_json(indent=2, by_alias=True)
        filename = f"{name}_layout.json"
    elif request.format == "tcl":
        content = _mock.export_constraints(request.layout)
        filename = f"{name}_constraints.tcl"
    else:
        content = _mock.export_def(request.layout)
        filename = f"{name}_floorplan.def"
    return ExportResponse(format=request.format, content=content, filename=filename)
