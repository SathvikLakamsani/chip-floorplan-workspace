"""Minimal DEF parser.

Not a full DEF-compliant parser — it extracts just enough to visualize an
imported floorplan: design name, units, die area, and the COMPONENTS section
(instance name, master cell, placement status, location, orientation).

Robustness over completeness: unknown/garbled lines are skipped rather than
raising. Returns a plain dict; mapping to the Layout model happens in
`openroad_importer`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DefComponent:
    instance: str
    master: str
    status: str = "PLACED"  # PLACED | FIXED | UNPLACED
    x: float = 0.0
    y: float = 0.0
    orientation: str = "N"


@dataclass
class DefData:
    version: str = ""
    design: str = ""
    units_per_micron: float | None = None
    die: tuple[float, float, float, float] | None = None  # x1,y1,x2,y2 (microns if units known)
    components: list[DefComponent] = field(default_factory=list)
    raw_units: bool = False  # True if we could not convert to microns
    warnings: list[str] = field(default_factory=list)


_ORIENT_MAP = {
    "N": "N", "S": "S", "E": "E", "W": "W",
    "FN": "FN", "FS": "FS", "FE": "FE", "FW": "FW",
    "R0": "N", "R90": "E", "R180": "S", "R270": "W",
    "MY": "FN", "MX": "FS", "MX90": "FE", "MY90": "FW",
}


def parse_def(path: str | Path) -> DefData:
    text = Path(path).read_text(errors="ignore")
    data = DefData()

    m = re.search(r"^\s*VERSION\s+([\d.]+)", text, re.MULTILINE)
    if m:
        data.version = m.group(1)

    m = re.search(r"^\s*DESIGN\s+(\S+)", text, re.MULTILINE)
    if m:
        data.design = m.group(1).strip(" ;")

    m = re.search(r"UNITS\s+DISTANCE\s+MICRONS\s+(\d+)", text)
    if m:
        data.units_per_micron = float(m.group(1))
    else:
        data.raw_units = True
        data.warnings.append("DEF has no UNITS DISTANCE MICRONS; coordinates kept as raw DBU.")

    scale = data.units_per_micron or 1.0

    # DIEAREA ( x1 y1 ) ( x2 y2 ) ;  (may have >2 points for rectilinear dies)
    m = re.search(r"DIEAREA\s+(.+?);", text, re.DOTALL)
    if m:
        pts = re.findall(r"\(\s*(-?\d+)\s+(-?\d+)\s*\)", m.group(1))
        if pts:
            xs = [int(p[0]) for p in pts]
            ys = [int(p[1]) for p in pts]
            data.die = (
                min(xs) / scale,
                min(ys) / scale,
                max(xs) / scale,
                max(ys) / scale,
            )

    _parse_components(text, data, scale)
    return data


def _parse_components(text: str, data: DefData, scale: float) -> None:
    block = re.search(r"COMPONENTS\s+\d+\s*;(.*?)END\s+COMPONENTS", text, re.DOTALL)
    if not block:
        return
    body = block.group(1)
    # Component records start with '-' and end with ';'. They may span lines.
    for record in re.split(r"(?=^\s*-\s)", body, flags=re.MULTILINE):
        record = record.strip()
        if not record.startswith("-"):
            continue
        record = record.rstrip(";").strip()
        m = re.match(r"-\s+(\S+)\s+(\S+)", record)
        if not m:
            continue
        comp = DefComponent(instance=m.group(1), master=m.group(2))
        placement = re.search(
            r"\+\s*(PLACED|FIXED|COVER|UNPLACED)\s*(?:\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*(\w+))?",
            record,
        )
        if placement:
            status = placement.group(1)
            comp.status = "FIXED" if status in ("FIXED", "COVER") else (
                "UNPLACED" if status == "UNPLACED" else "PLACED"
            )
            if placement.group(2) is not None:
                comp.x = int(placement.group(2)) / scale
                comp.y = int(placement.group(3)) / scale
                comp.orientation = _ORIENT_MAP.get(placement.group(4) or "N", "N")
        else:
            comp.status = "UNPLACED"
        data.components.append(comp)
