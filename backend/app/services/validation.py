"""Placement legality / DRC-style checks.

These are intentionally simplified, geometry-level checks for UX feedback — not
real signoff DRC/LVS. They flag common floorplanning problems (overlaps, halo
violations, blocks outside the core, IOs off the die edge, over-utilization,
congestion, timing) with severities and human-readable suggested fixes.
"""

from __future__ import annotations

import itertools

from app.models.layout import (
    Block,
    BlockClass,
    DRCReport,
    DRCViolation,
    Layout,
    Rect,
    Severity,
)

VALID_ORIENTATIONS = {"N", "S", "E", "W", "FN", "FS", "FE", "FW"}


class ValidationEngine:
    """Run legality/DRC-style checks and return a structured report."""

    def check(self, layout: Layout, metrics=None) -> DRCReport:
        violations: list[DRCViolation] = []
        vid = itertools.count(1)

        def new_id() -> str:
            return f"drc_{next(vid)}"

        blocks = layout.blocks
        core = layout.chip.core

        # --- Block-vs-block overlap -------------------------------------
        for a, b in itertools.combinations(blocks, 2):
            ox, oy = self._overlap(a, b)
            if ox > 0.5 and oy > 0.5:
                violations.append(
                    DRCViolation(
                        id=new_id(),
                        severity=Severity.ERROR,
                        rule="block_overlap",
                        message=f"{a.name} overlaps {b.name} ({ox:.0f}×{oy:.0f} μm).",
                        targets=[a.id, b.id],
                        region=Rect(
                            x=max(a.x, b.x),
                            y=max(a.y, b.y),
                            width=ox,
                            height=oy,
                        ),
                        suggestion=(
                            f"Move {b.name} clear of {a.name}, or run "
                            f"'make sure none of the parts are touching'."
                        ),
                    )
                )

        # --- Halo overlap (hard macros) ---------------------------------
        for a, b in itertools.combinations(blocks, 2):
            if a.halo is None and b.halo is None:
                continue
            ox, oy = self._overlap(a, b, halo=True)
            base_ox, base_oy = self._overlap(a, b)
            if ox > 0.5 and oy > 0.5 and not (base_ox > 0.5 and base_oy > 0.5):
                violations.append(
                    DRCViolation(
                        id=new_id(),
                        severity=Severity.WARNING,
                        rule="halo_overlap",
                        message=(
                            f"Halo/keepout of {a.name} and {b.name} overlap — "
                            "insufficient macro spacing."
                        ),
                        targets=[a.id, b.id],
                        suggestion=f"Increase spacing between {a.name} and {b.name}.",
                    )
                )

        # --- Blocks outside the core ------------------------------------
        if core is not None:
            for block in blocks:
                if self._is_io(block):
                    continue
                if not self._inside(block, core):
                    violations.append(
                        DRCViolation(
                            id=new_id(),
                            severity=Severity.WARNING,
                            rule="outside_core",
                            message=f"{block.name} extends outside the core area.",
                            targets=[block.id],
                            suggestion=f"Move {block.name} fully inside the core boundary.",
                        )
                    )

        # --- IO not near die boundary -----------------------------------
        die = layout.chip.die
        if die is not None:
            margin = min(die.width, die.height) * 0.12
            for block in blocks:
                if not self._is_io(block):
                    continue
                if not self._near_die_edge(block, die, margin):
                    violations.append(
                        DRCViolation(
                            id=new_id(),
                            severity=Severity.INFO,
                            rule="io_placement",
                            message=f"IO block {block.name} is not near the die boundary.",
                            targets=[block.id],
                            suggestion=f"Place {block.name} along a die edge.",
                        )
                    )

        # --- Soft logic too close to hard macros ------------------------
        macros = [b for b in blocks if self._is_hard_macro(b)]
        soft = [b for b in blocks if self._is_soft_logic(b)]
        for macro in macros:
            for s in soft:
                gap_x, gap_y = self._gap(macro, s)
                if -0.5 < gap_x < 8 and gap_y < 0:
                    pass  # handled by overlap
                elif 0 <= gap_x < 8 and 0 <= gap_y < 8:
                    violations.append(
                        DRCViolation(
                            id=new_id(),
                            severity=Severity.INFO,
                            rule="soft_near_macro",
                            message=(
                                f"Soft logic {s.name} is very close to hard macro "
                                f"{macro.name}."
                            ),
                            targets=[macro.id, s.id],
                            suggestion=f"Add a small halo around {macro.name}.",
                        )
                    )

        # --- Invalid orientation ----------------------------------------
        for block in blocks:
            orient = (
                block.orientation
                if isinstance(block.orientation, str)
                else block.orientation.value
            )
            if orient not in VALID_ORIENTATIONS:
                violations.append(
                    DRCViolation(
                        id=new_id(),
                        severity=Severity.WARNING,
                        rule="invalid_orientation",
                        message=f"{block.name} has invalid orientation '{orient}'.",
                        targets=[block.id],
                        suggestion="Use one of N, S, E, W, FN, FS, FE, FW.",
                    )
                )

        # --- Metric-driven checks ---------------------------------------
        if metrics is not None:
            if metrics.area_utilization > 0.85:
                violations.append(
                    DRCViolation(
                        id=new_id(),
                        severity=Severity.WARNING,
                        rule="high_utilization",
                        message=(
                            f"Area utilization {metrics.area_utilization:.0%} is high — "
                            "routing may be difficult."
                        ),
                        suggestion="Enlarge the die/core or reduce block sizes.",
                    )
                )
            if metrics.congestion_score > 0.8:
                violations.append(
                    DRCViolation(
                        id=new_id(),
                        severity=Severity.WARNING,
                        rule="high_congestion",
                        message=(
                            f"Congestion score {metrics.congestion_score:.2f} is high."
                        ),
                        suggestion="Spread densely connected blocks to open routing channels.",
                    )
                )
            if metrics.wns < 0:
                violations.append(
                    DRCViolation(
                        id=new_id(),
                        severity=Severity.WARNING,
                        rule="negative_wns",
                        message=(
                            f"Negative WNS ({metrics.wns} ns): "
                            f"{metrics.violating_paths} paths violate timing."
                        ),
                        suggestion="Move timing-critical connected blocks closer together.",
                    )
                )

        return DRCReport(violations=violations)

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------
    def _overlap(self, a: Block, b: Block, halo: bool = False) -> tuple[float, float]:
        ax1, ay1, ax2, ay2 = self._extent(a, halo)
        bx1, by1, bx2, by2 = self._extent(b, halo)
        ox = min(ax2, bx2) - max(ax1, bx1)
        oy = min(ay2, by2) - max(ay1, by1)
        return max(0.0, ox), max(0.0, oy)

    def _gap(self, a: Block, b: Block) -> tuple[float, float]:
        ax1, ay1, ax2, ay2 = self._extent(a)
        bx1, by1, bx2, by2 = self._extent(b)
        gap_x = max(bx1 - ax2, ax1 - bx2)
        gap_y = max(by1 - ay2, ay1 - by2)
        return gap_x, gap_y

    def _extent(self, b: Block, halo: bool = False) -> tuple[float, float, float, float]:
        x1, y1 = b.x, b.y
        x2, y2 = b.x + b.width, b.y + b.height
        if halo and b.halo is not None:
            x1 -= b.halo.left
            y1 -= b.halo.top
            x2 += b.halo.right
            y2 += b.halo.bottom
        return x1, y1, x2, y2

    def _inside(self, b: Block, rect: Rect) -> bool:
        return (
            b.x >= rect.x - 0.5
            and b.y >= rect.y - 0.5
            and b.x + b.width <= rect.x + rect.width + 0.5
            and b.y + b.height <= rect.y + rect.height + 0.5
        )

    def _near_die_edge(self, b: Block, die: Rect, margin: float) -> bool:
        left = b.x - die.x
        top = b.y - die.y
        right = (die.x + die.width) - (b.x + b.width)
        bottom = (die.y + die.height) - (b.y + b.height)
        return min(left, top, right, bottom) <= margin

    def _is_io(self, b: Block) -> bool:
        return self._cls(b) == BlockClass.IO.value or self._type(b) == "io"

    def _is_hard_macro(self, b: Block) -> bool:
        return self._cls(b) in (
            BlockClass.HARD_MACRO.value,
            BlockClass.MEMORY.value,
        )

    def _is_soft_logic(self, b: Block) -> bool:
        return self._cls(b) in (
            BlockClass.SOFT_LOGIC.value,
            BlockClass.STANDARD_CELL_REGION.value,
        )

    def _cls(self, b: Block) -> str:
        return b.cls if isinstance(b.cls, str) else b.cls.value

    def _type(self, b: Block) -> str:
        return b.type if isinstance(b.type, str) else b.type.value
