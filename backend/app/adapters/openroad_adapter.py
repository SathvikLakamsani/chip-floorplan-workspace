"""OpenROAD Flow Scripts adapter (stub for future integration).

TODO: Real OpenROAD Flow Scripts integration
TODO: DEF parser for loading floorplan geometry
TODO: LEF parser for macro dimensions and pin locations
TODO: Timing report parser (OpenSTA format)
TODO: Congestion report parser (FastRoute/OpenROAD format)
TODO: Tcl constraint export compatible with ORFS flow
TODO: OpenROAD rerun pipeline (floorplan -> placement -> routing -> STA)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.adapters.base import EDAAdapter
from app.models.layout import Layout, Metrics


class OpenROADAdapter(EDAAdapter):
    """Future adapter that will invoke OpenROAD Flow Scripts."""

    def __init__(self, orfs_root: Path | None = None) -> None:
        self.orfs_root = orfs_root or Path(__file__).resolve().parents[4]

    def run_floorplan(self, layout: Layout) -> Layout:
        raise NotImplementedError(
            "OpenROAD floorplan integration not yet implemented. "
            "Use MockEDAAdapter for MVP."
        )

    def run_placement(self, layout: Layout) -> Layout:
        raise NotImplementedError("OpenROAD placement integration not yet implemented.")

    def run_routing(self, layout: Layout) -> Layout:
        raise NotImplementedError("OpenROAD routing integration not yet implemented.")

    def run_timing(self, layout: Layout) -> Metrics:
        raise NotImplementedError("OpenROAD STA integration not yet implemented.")

    def parse_reports(self, run_dir: Path) -> dict[str, Any]:
        raise NotImplementedError(
            "OpenROAD report parsing not yet implemented. "
            "See report_parser.py for mock format support."
        )

    def export_constraints(self, layout: Layout) -> str:
        raise NotImplementedError("OpenROAD Tcl export not yet implemented.")
