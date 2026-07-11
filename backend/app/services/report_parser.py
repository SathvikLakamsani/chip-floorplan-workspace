"""Parser for OpenROAD/OpenLane-style reports (mock format for MVP).

TODO: Real timing report parser (OpenSTA .rpt format)
TODO: Real congestion report parser (FastRoute/OpenROAD .rpt)
TODO: DEF parser for floorplan geometry
TODO: LEF parser for macro pin locations
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


class ReportParser:
    """Parse mock and future real EDA reports."""

    def parse_timing_report(self, content: str) -> dict[str, float]:
        """Parse timing report text."""
        result: dict[str, float] = {}
        wns_match = re.search(r"WNS\s*[:=]\s*(-?\d+\.?\d*)\s*ns", content, re.IGNORECASE)
        tns_match = re.search(r"TNS\s*[:=]\s*(-?\d+\.?\d*)\s*ns", content, re.IGNORECASE)
        if wns_match:
            result["wns"] = float(wns_match.group(1))
        if tns_match:
            result["tns"] = float(tns_match.group(1))
        return result

    def parse_congestion_report(self, content: str) -> dict[str, float]:
        """Parse congestion report text."""
        result: dict[str, float] = {}
        score_match = re.search(
            r"(?:congestion|overflow)\s*(?:score)?\s*[:=]\s*(\d+\.?\d*)",
            content,
            re.IGNORECASE,
        )
        util_match = re.search(
            r"(?:area\s*)?utilization\s*[:=]\s*(\d+\.?\d*)%?",
            content,
            re.IGNORECASE,
        )
        if score_match:
            val = float(score_match.group(1))
            result["congestion_score"] = val / 100 if val > 1 else val
        if util_match:
            val = float(util_match.group(1))
            result["area_utilization"] = val / 100 if val > 1 else val
        return result

    def parse_wire_length_report(self, content: str) -> dict[str, float]:
        result: dict[str, float] = {}
        wl_match = re.search(
            r"(?:total\s*)?wire\s*length\s*[:=]\s*(\d+\.?\d*)",
            content,
            re.IGNORECASE,
        )
        if wl_match:
            result["wire_length"] = float(wl_match.group(1))
        return result

    def parse_run_directory(self, run_dir: Path) -> dict[str, Any]:
        """Parse all reports in a mock run directory."""
        metrics: dict[str, Any] = {}
        if not run_dir.exists():
            return metrics

        timing_file = run_dir / "timing.rpt"
        if timing_file.exists():
            metrics.update(self.parse_timing_report(timing_file.read_text()))

        congestion_file = run_dir / "congestion.rpt"
        if congestion_file.exists():
            metrics.update(self.parse_congestion_report(congestion_file.read_text()))

        wire_file = run_dir / "wire_length.rpt"
        if wire_file.exists():
            metrics.update(self.parse_wire_length_report(wire_file.read_text()))

        return metrics
