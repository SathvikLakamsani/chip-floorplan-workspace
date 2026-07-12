"""Lightweight congestion report parser.

Attempts to extract spatial congestion regions. Many OpenROAD congestion dumps
are grid-based or free-form; if we can find coordinate/score tuples we build
CongestionRegion entries, otherwise we return a single generic warning.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.models.layout import CongestionRegion

# Matches lines like: "GCell (12, 34)  h_util 0.85 v_util 0.9"
# or "region 100 200 180 160 0.82"
_XYWHS = re.compile(
    r"(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(0?\.\d+|1\.0+)"
)
_UTIL = re.compile(r"\(?\s*(\d+)\s*,\s*(\d+)\s*\)?.*?(?:util|congestion)\D*(0?\.\d+|1\.0+)", re.IGNORECASE)


def parse_congestion_report(
    path: str | Path,
) -> tuple[list[CongestionRegion], list[str]]:
    text = Path(path).read_text(errors="ignore")
    regions: list[CongestionRegion] = []
    warnings: list[str] = []

    for m in _XYWHS.finditer(text):
        x, y, w, h, score = (float(g) for g in m.groups())
        if w <= 0 or h <= 0:
            continue
        regions.append(
            CongestionRegion(
                x=x, y=y, width=w, height=h,
                score=min(1.0, score),
                reason="Imported congestion region.",
            )
        )

    if not regions:
        for m in _UTIL.finditer(text):
            gx, gy, score = int(m.group(1)), int(m.group(2)), float(m.group(3))
            regions.append(
                CongestionRegion(
                    x=gx * 20.0, y=gy * 20.0, width=20.0, height=20.0,
                    score=min(1.0, score),
                    reason="Imported GCell utilization.",
                )
            )

    if not regions:
        warnings.append(
            "Congestion report found, but spatial regions could not be parsed."
        )
    else:
        regions.sort(key=lambda r: r.score, reverse=True)
        regions = regions[:20]
        warnings.append(f"Parsed {len(regions)} congestion region(s).")
    return regions, warnings
