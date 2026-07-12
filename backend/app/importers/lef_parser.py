"""Minimal LEF parser.

Extracts MACRO name, CLASS, ORIGIN, SIZE (width BY height) and PIN names +
directions. Used to size imported DEF components and to attach pin markers.
Best-effort: malformed macros are skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LefPin:
    name: str
    direction: str = ""


@dataclass
class LefMacro:
    name: str
    cls: str = ""
    width: float = 0.0
    height: float = 0.0
    origin: tuple[float, float] = (0.0, 0.0)
    pins: list[LefPin] = field(default_factory=list)


def parse_lef(path: str | Path) -> dict[str, LefMacro]:
    text = Path(path).read_text(errors="ignore")
    macros: dict[str, LefMacro] = {}

    for m in re.finditer(r"MACRO\s+(\S+)(.*?)END\s+\1", text, re.DOTALL):
        name = m.group(1)
        body = m.group(2)
        macro = LefMacro(name=name)

        cls = re.search(r"\bCLASS\s+([A-Z ]+?);", body)
        if cls:
            macro.cls = cls.group(1).strip()

        size = re.search(r"\bSIZE\s+([\d.]+)\s+BY\s+([\d.]+)\s*;", body)
        if size:
            macro.width = float(size.group(1))
            macro.height = float(size.group(2))

        origin = re.search(r"\bORIGIN\s+([\d.-]+)\s+([\d.-]+)\s*;", body)
        if origin:
            macro.origin = (float(origin.group(1)), float(origin.group(2)))

        for pm in re.finditer(r"\bPIN\s+(\S+)(.*?)END\s+\1", body, re.DOTALL):
            pin = LefPin(name=pm.group(1))
            d = re.search(r"\bDIRECTION\s+(\w+)\s*;", pm.group(2))
            if d:
                pin.direction = d.group(1)
            macro.pins.append(pin)

        macros[name] = macro

    return macros
