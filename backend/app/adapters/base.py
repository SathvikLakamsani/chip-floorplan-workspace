"""EDA adapter interface for OpenROAD/OpenLane integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.models.layout import Layout, Metrics


class EDAAdapter(ABC):
    """Abstract interface for EDA tool integration."""

    @abstractmethod
    def run_floorplan(self, layout: Layout) -> Layout:
        """Run automated floorplanning on the given layout."""

    @abstractmethod
    def run_placement(self, layout: Layout) -> Layout:
        """Run placement optimization."""

    @abstractmethod
    def run_routing(self, layout: Layout) -> Layout:
        """Run global/detailed routing."""

    @abstractmethod
    def run_timing(self, layout: Layout) -> Metrics:
        """Run static timing analysis and return metrics."""

    @abstractmethod
    def parse_reports(self, run_dir: Path) -> dict[str, Any]:
        """Parse timing, congestion, and area reports from a run directory."""

    @abstractmethod
    def export_constraints(self, layout: Layout) -> str:
        """Export layout constraints as Tcl or other EDA format."""
