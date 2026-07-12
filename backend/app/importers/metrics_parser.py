"""Flexible metrics JSON parser.

OpenROAD/OpenLane emit metrics under many different key names across versions
(e.g. `finish__timing__setup__ws`, `timing__setup__wns`, `worst_slack`, ...).
This parser flattens nested JSON and matches fields by case-insensitive
substring so it works across formats. Missing metrics are left as defaults and
recorded as warnings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models.layout import Metrics

# metric field -> list of substrings that (all-or-any) identify it.
# Each entry is a list of "any of these substrings" groups; a key matches if it
# contains at least one substring from every group.
_MATCHERS: dict[str, list[list[str]]] = {
    "wns": [["wns"]],
    "wns_alt": [["worst"], ["slack"]],
    "wns_ws": [["setup"], ["ws"]],
    "tns": [["tns"]],
    "tns_alt": [["total"], ["negative", "slack"]],
    "violating_paths": [["violating"]],
    "wire_length": [["wire"], ["length"]],
    "wire_length_alt": [["wirelength"]],
    "congestion_score": [["congestion"]],
    "area_utilization": [["util"]],
    "power_estimate": [["power"], ["total"]],
    "power_alt": [["power"]],
    "drc_count": [["drc"]],
    "drc_alt": [["violations"]],
}


def _flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            flat.update(_flatten(v, key))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            flat.update(_flatten(v, f"{prefix}.{i}"))
    else:
        flat[prefix] = obj
    return flat


def _match(flat: dict[str, Any], groups: list[list[str]]) -> Any:
    for key, value in flat.items():
        lk = key.lower()
        if all(any(sub in lk for sub in group) for group in groups):
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def parse_metrics_files(paths: list[str | Path]) -> tuple[Metrics, list[str]]:
    warnings: list[str] = []
    flat: dict[str, Any] = {}
    for p in paths:
        try:
            data = json.loads(Path(p).read_text(errors="ignore"))
            flat.update(_flatten(data))
        except (json.JSONDecodeError, OSError) as exc:
            warnings.append(f"Could not parse metrics file {Path(p).name}: {exc}")

    if not flat:
        return Metrics(), ["No parseable metrics JSON found; using defaults."]

    def pick(*names: str) -> float | None:
        for n in names:
            if n in _MATCHERS:
                v = _match(flat, _MATCHERS[n])
                if v is not None:
                    return v
        return None

    metrics = Metrics()
    found: list[str] = []

    wns = pick("wns", "wns_alt", "wns_ws")
    if wns is not None:
        metrics.wns = round(wns, 3)
        found.append("WNS")
    tns = pick("tns", "tns_alt")
    if tns is not None:
        metrics.tns = round(tns, 3)
        found.append("TNS")
    vp = pick("violating_paths")
    if vp is not None:
        metrics.violating_paths = int(vp)
        found.append("violating_paths")
    wl = pick("wire_length", "wire_length_alt")
    if wl is not None:
        metrics.wire_length = round(wl, 1)
        found.append("wire_length")
    util = pick("area_utilization")
    if util is not None:
        metrics.area_utilization = min(1.0, util if util <= 1 else util / 100.0)
        found.append("utilization")
    cong = pick("congestion_score")
    if cong is not None:
        metrics.congestion_score = min(1.0, cong if cong <= 1 else cong / 100.0)
        found.append("congestion")
    power = pick("power_estimate", "power_alt")
    if power is not None:
        metrics.power_estimate = round(power, 3)
        found.append("power")
    drc = pick("drc_count", "drc_alt")
    if drc is not None:
        metrics.drc_count = int(drc)
        found.append("drc_count")

    if found:
        warnings.append(f"Parsed metrics: {', '.join(found)}.")
    else:
        warnings.append("Metrics JSON found but no recognizable QoR fields matched.")
    return metrics, warnings
