"""EDA adapter abstraction.

The app treats OpenROAD/OpenLane as an external engine behind an adapter
interface, rather than embedding EDA logic. Two adapters ship today:

- ``MockEDAAdapter``: computes approximate metrics locally (no EDA install).
- ``OpenROADImportAdapter``: imports an *existing* OpenROAD/OpenLane run
  directory (offline). It does NOT launch OpenROAD.

A future ``OpenROADFlowScriptsAdapter`` (see TODOs) would actually shell out to
ORFS/OpenLane to run floorplan → placement → routing → STA.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.importers.openroad_importer import import_run as _import_run
from app.models.layout import ImportResponse, Layout, Metrics
from app.services.analysis_engine import AnalysisEngine


class EDAAdapter(ABC):
    """Abstract interface for EDA tool integration."""

    @abstractmethod
    def import_run(self, path: str) -> ImportResponse:
        """Import an existing OpenROAD/OpenLane run directory (offline)."""

    @abstractmethod
    def run_floorplan(self, layout: Layout) -> Layout:
        ...

    @abstractmethod
    def run_placement(self, layout: Layout) -> Layout:
        ...

    @abstractmethod
    def run_routing(self, layout: Layout) -> Layout:
        ...

    @abstractmethod
    def run_timing(self, layout: Layout) -> Metrics:
        ...

    @abstractmethod
    def parse_reports(self, run_dir: Path) -> ImportResponse:
        ...

    @abstractmethod
    def export_constraints(self, layout: Layout) -> str:
        """Export placement constraints (Tcl placeholder)."""

    @abstractmethod
    def export_def(self, layout: Layout) -> str:
        """Export a simplified DEF placeholder."""


class MockEDAAdapter(EDAAdapter):
    """Local mock: uses the internal analysis engine, no external tools."""

    def __init__(self) -> None:
        self._engine = AnalysisEngine()

    def import_run(self, path: str) -> ImportResponse:
        return _import_run(path)

    def run_floorplan(self, layout: Layout) -> Layout:
        layout.metrics = self._engine.analyze(layout)
        return self._engine.enrich(layout)

    def run_placement(self, layout: Layout) -> Layout:
        return self.run_floorplan(layout)

    def run_routing(self, layout: Layout) -> Layout:
        return self.run_floorplan(layout)

    def run_timing(self, layout: Layout) -> Metrics:
        return self._engine.analyze(layout)

    def parse_reports(self, run_dir: Path) -> ImportResponse:
        return _import_run(str(run_dir))

    def export_constraints(self, layout: Layout) -> str:
        return export_tcl(layout)

    def export_def(self, layout: Layout) -> str:
        return export_def(layout)


class OpenROADImportAdapter(EDAAdapter):
    """Offline import adapter for real OpenROAD/OpenLane output.

    Only reads existing run data. Any "run_*" step raises NotImplementedError —
    live execution is intentionally out of scope for the MVP.
    """

    def __init__(self) -> None:
        self._engine = AnalysisEngine()

    def import_run(self, path: str) -> ImportResponse:
        resp = _import_run(path)
        # If the run had no metrics, estimate them so the UI has QoR data.
        if resp.layout is not None and resp.layout.metrics is None:
            resp.layout.metrics = self._engine.analyze(resp.layout)
            self._engine.enrich(resp.layout)
            resp.warnings.append("Metrics estimated locally (none found in run).")
        return resp

    def parse_reports(self, run_dir: Path) -> ImportResponse:
        return self.import_run(str(run_dir))

    def run_floorplan(self, layout: Layout) -> Layout:
        raise NotImplementedError(
            "Live OpenROAD floorplan execution is not implemented. "
            "Run OpenROAD/OpenLane separately and import the run directory."
        )

    def run_placement(self, layout: Layout) -> Layout:
        raise NotImplementedError("Live OpenROAD placement not implemented (offline import only).")

    def run_routing(self, layout: Layout) -> Layout:
        raise NotImplementedError("Live OpenROAD routing not implemented (offline import only).")

    def run_timing(self, layout: Layout) -> Metrics:
        raise NotImplementedError("Live OpenSTA not implemented (offline import only).")

    def export_constraints(self, layout: Layout) -> str:
        return export_tcl(layout)

    def export_def(self, layout: Layout) -> str:
        return export_def(layout)


# TODO: OpenROADFlowScriptsAdapter — actually launch OpenROAD Flow Scripts:
#   - run_floorplan(): invoke `make DESIGN_CONFIG=... floorplan`
#   - run_placement()/run_routing()/run_timing(): drive the ORFS make targets
#   - parse_reports(): read results/ + reports/ and reuse the importers here
#   - export a real Tcl constraints file consumable by ORFS
# TODO: OpenLane2Adapter — same idea against the OpenLane 2 (Python) flow.


# ----------------------------------------------------------------------
# Export placeholders (simplified, not signoff-quality)
# ----------------------------------------------------------------------
def export_tcl(layout: Layout) -> str:
    lines = [
        "# Floorplan constraints generated by AI floorplan copilot",
        "# TODO: convert to fully OpenROAD-compatible Tcl",
        f"# design: {layout.chip.name}",
        "",
    ]
    if layout.chip.die:
        d = layout.chip.die
        lines.append(f"# die area: {d.width:.1f} x {d.height:.1f} {layout.chip.unit}")
    for b in layout.blocks:
        cls = b.cls if isinstance(b.cls, str) else b.cls.value
        if cls == "standard_cell_region":
            continue
        orient = b.orientation if isinstance(b.orientation, str) else b.orientation.value
        lines.append(f"set_block_location {b.id} {b.x:.1f} {b.y:.1f} {orient}")
        if b.fixed:
            lines.append(f"set_block_fixed {b.id} true")
        if b.keepout and b.halo:
            lines.append(f"create_keepout {b.id} {b.halo.left:.0f}")
    for c in layout.constraints:
        lines.append(f"# constraint {c.type}: {c.description} -> {', '.join(c.targets)}")
    return "\n".join(lines) + "\n"


def export_def(layout: Layout) -> str:
    d = layout.chip.die
    scale = 1000  # DBU per micron placeholder
    lines = [
        "# Simplified DEF placeholder generated by AI floorplan copilot",
        "# TODO: emit signoff-quality DEF",
        "VERSION 5.8 ;",
        f"DESIGN {layout.chip.name} ;",
        f"UNITS DISTANCE MICRONS {scale} ;",
    ]
    if d:
        lines.append(
            f"DIEAREA ( {int(d.x*scale)} {int(d.y*scale)} ) "
            f"( {int((d.x+d.width)*scale)} {int((d.y+d.height)*scale)} ) ;"
        )
    placeable = [
        b for b in layout.blocks
        if (b.cls if isinstance(b.cls, str) else b.cls.value) != "standard_cell_region"
    ]
    lines.append(f"COMPONENTS {len(placeable)} ;")
    for b in placeable:
        orient = b.orientation if isinstance(b.orientation, str) else b.orientation.value
        status = "FIXED" if b.fixed else "PLACED"
        lines.append(
            f"    - {b.id} {b.id}_MASTER + {status} "
            f"( {int(b.x*scale)} {int(b.y*scale)} ) {orient} ;"
        )
    lines.append("END COMPONENTS")
    lines.append("END DESIGN")
    return "\n".join(lines) + "\n"
