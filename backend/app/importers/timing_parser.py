"""Lightweight OpenSTA-style timing report parser.

Extracts up to N critical paths (startpoint, endpoint, slack, clock/group) from
a text report. OpenSTA `report_checks` output typically looks like:

    Startpoint: reg_a (rising edge-triggered ...)
    Endpoint: reg_b (rising edge-triggered ...)
    Path Group: core_clk
    ...
    slack (VIOLATED)   -0.12

This is best-effort; if nothing parses it returns an empty list and a warning
rather than crashing.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.models.layout import TimingPath


def parse_timing_report(path: str | Path, limit: int = 5) -> tuple[list[TimingPath], list[str]]:
    text = Path(path).read_text(errors="ignore")
    paths: list[TimingPath] = []
    warnings: list[str] = []

    # Split into per-path blocks on "Startpoint:".
    blocks = re.split(r"(?=Startpoint:)", text)
    idx = 0
    for block in blocks:
        sp = re.search(r"Startpoint:\s*(\S+)", block)
        ep = re.search(r"Endpoint:\s*(\S+)", block)
        slack = re.search(r"slack\s*(?:\(\w+\))?\s*(-?\d+\.?\d*)", block, re.IGNORECASE)
        if not (sp and ep and slack):
            continue
        group = re.search(r"Path Group:\s*(\S+)", block)
        idx += 1
        s = float(slack.group(1))
        paths.append(
            TimingPath(
                id=f"import_path_{idx}",
                startpoint=sp.group(1),
                endpoint=ep.group(1),
                slack=round(s, 4),
                criticality=1.0 if s < 0 else 0.5,
                clock=group.group(1) if group else "",
                explanation="Imported from timing report.",
            )
        )

    if not paths:
        warnings.append("Timing report found, but no critical paths could be parsed.")
    else:
        paths.sort(key=lambda p: p.slack)
        paths = paths[:limit]
        warnings.append(f"Parsed {len(paths)} timing path(s) from report.")
    return paths, warnings
