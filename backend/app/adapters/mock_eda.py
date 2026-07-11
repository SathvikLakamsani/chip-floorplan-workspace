"""Mock EDA adapter for MVP development and testing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.adapters.base import EDAAdapter
from app.models.layout import Layout, Metrics
from app.services.analysis_engine import AnalysisEngine


class MockEDAAdapter(EDAAdapter):
    """Mock adapter that uses the internal analysis engine."""

    def __init__(self) -> None:
        self._engine = AnalysisEngine()

    def run_floorplan(self, layout: Layout) -> Layout:
        metrics = self._engine.analyze(layout)
        layout.metrics = metrics
        return layout

    def run_placement(self, layout: Layout) -> Layout:
        return self.run_floorplan(layout)

    def run_routing(self, layout: Layout) -> Layout:
        metrics = self._engine.analyze(layout)
        layout.metrics = metrics
        return layout

    def run_timing(self, layout: Layout) -> Metrics:
        return self._engine.analyze(layout)

    def parse_reports(self, run_dir: Path) -> dict[str, Any]:
        from app.services.report_parser import ReportParser

        parser = ReportParser()
        return parser.parse_run_directory(run_dir)

    def export_constraints(self, layout: Layout) -> str:
        lines = ["# Floorplan constraints (mock export)"]
        for block in layout.blocks:
            status = "FIXED" if block.fixed else "PLACED"
            lines.append(
                f"# {status} {block.id}: ({block.x}, {block.y}) "
                f"{block.width}x{block.height}"
            )
        for constraint in layout.constraints:
            lines.append(f"# CONSTRAINT {constraint.type}: {constraint.description}")
            lines.append(f"#   targets: {', '.join(constraint.targets)}")
        # TODO: Implement real Tcl constraint export for OpenROAD
        return "\n".join(lines)
