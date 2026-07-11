"""Layout mutation operations applied from structured command actions."""

from __future__ import annotations

import copy
import math

from app.models.layout import ActionType, Block, CommandAction, Layout
from app.services.analysis_engine import AnalysisEngine


class LayoutOperations:
    """Apply structured actions to a layout."""

    def __init__(self) -> None:
        self._engine = AnalysisEngine()

    def apply_actions(self, layout: Layout, actions: list[CommandAction]) -> Layout:
        result = copy.deepcopy(layout)
        for action in actions:
            action_type = action.type if isinstance(action.type, str) else action.type.value
            if action_type == ActionType.MOVE_BLOCKS.value:
                self._move_blocks(result, action)
            elif action_type == ActionType.LOCK_BLOCKS.value:
                self._lock_blocks(result, action)
            elif action_type == ActionType.RESIZE_BLOCKS.value:
                self._resize_blocks(result, action)
            elif action_type == ActionType.UPDATE_PROPERTY.value:
                self._update_property(result, action)
        result.metrics = self._engine.analyze(result)
        return result

    def generate_candidates(self, layout: Layout, count: int = 3) -> list[tuple[Layout, str]]:
        """Generate layout candidates with different optimization strategies."""
        baseline_metrics = self._engine.analyze(layout)
        candidates: list[tuple[Layout, str]] = []

        # Candidate A: timing — move SRAM closer to compute
        timing_layout = copy.deepcopy(layout)
        compute = self._find_block(timing_layout, "compute_array")
        if compute:
            for block in timing_layout.blocks:
                if block.type == "sram" and not block.fixed:
                    self._move_toward(block, compute, factor=0.4)
        timing_layout.metrics = self._engine.analyze(timing_layout)
        candidates.append(
            (
                timing_layout,
                "Candidate A improves timing by moving SRAM banks closer to the compute array, "
                "reducing critical path wire length.",
            )
        )

        # Candidate B: congestion — spread memory and NoC
        congestion_layout = copy.deepcopy(layout)
        noc = self._find_block(congestion_layout, "noc_router")
        mem_ctrl = self._find_block(congestion_layout, "memory_controller")
        for block in congestion_layout.blocks:
            if not block.fixed and block.id in {
                b.id
                for b in congestion_layout.blocks
                if b.type in ("sram", "noc", "controller")
            }:
                if noc and block.id != noc.id:
                    self._move_away(block, noc, factor=30)
                if mem_ctrl and block.id != mem_ctrl.id:
                    self._move_away(block, mem_ctrl, factor=20)
        congestion_layout.metrics = self._engine.analyze(congestion_layout)
        candidates.append(
            (
                congestion_layout,
                "Candidate B reduces congestion by increasing spacing between memory blocks "
                "and the NoC router.",
            )
        )

        # Candidate C: area — compact layout
        area_layout = copy.deepcopy(layout)
        center_x = layout.chip.width / 2
        center_y = layout.chip.height / 2
        for block in area_layout.blocks:
            if not block.fixed:
                bcx = block.x + block.width / 2
                bcy = block.y + block.height / 2
                block.x += (center_x - bcx) * 0.15
                block.y += (center_y - bcy) * 0.15
        area_layout.metrics = self._engine.analyze(area_layout)
        candidates.append(
            (
                area_layout,
                "Candidate C minimizes area by compacting blocks toward the chip center, "
                "but may worsen routing congestion.",
            )
        )

        return candidates[:count]

    def _move_blocks(self, layout: Layout, action: CommandAction) -> None:
        params = action.params
        mode = params.get("mode", "anchor")

        if mode == "timing_optimize":
            self._timing_optimize(layout, action.targets)
        elif mode == "spread":
            self._spread_blocks(layout, action.targets, params.get("factor", 1.2))
        elif mode == "delta":
            self._move_delta(
                layout,
                action.targets,
                float(params.get("dx", 0) or 0),
                float(params.get("dy", 0) or 0),
            )
        elif mode == "absolute":
            self._move_absolute(layout, action.targets, params.get("x"), params.get("y"))
        elif mode == "region":
            self._move_region(
                layout,
                action.targets,
                str(params.get("region", "center")),
                float(params.get("factor", 0.5) or 0.5),
            )
        else:  # "toward" / "anchor"
            anchor_id = params.get("anchor", "compute_array")
            factor = params.get("factor", 0.35)
            anchor = self._find_block(layout, anchor_id)
            if not anchor:
                return
            for block in layout.blocks:
                if block.id in action.targets and not block.fixed:
                    self._move_toward(block, anchor, factor)

    def _move_delta(
        self, layout: Layout, targets: list[str], dx: float, dy: float
    ) -> None:
        for block in layout.blocks:
            if block.id in targets and not block.fixed:
                block.x = self._clamp_x(layout, block, block.x + dx)
                block.y = self._clamp_y(layout, block, block.y + dy)

    def _move_absolute(
        self, layout: Layout, targets: list[str], x, y
    ) -> None:
        for block in layout.blocks:
            if block.id in targets and not block.fixed:
                if x is not None:
                    block.x = self._clamp_x(layout, block, float(x))
                if y is not None:
                    block.y = self._clamp_y(layout, block, float(y))

    def _move_region(
        self, layout: Layout, targets: list[str], region: str, factor: float
    ) -> None:
        w, h = layout.chip.width, layout.chip.height
        anchors = {
            "top_left": (w * 0.2, h * 0.2),
            "top_right": (w * 0.8, h * 0.2),
            "bottom_left": (w * 0.2, h * 0.8),
            "bottom_right": (w * 0.8, h * 0.8),
            "center": (w * 0.5, h * 0.5),
        }
        tx, ty = anchors.get(region, anchors["center"])
        for block in layout.blocks:
            if block.id in targets and not block.fixed:
                bcx = block.x + block.width / 2
                bcy = block.y + block.height / 2
                block.x = self._clamp_x(layout, block, block.x + (tx - bcx) * factor)
                block.y = self._clamp_y(layout, block, block.y + (ty - bcy) * factor)

    def _clamp_x(self, layout: Layout, block: Block, x: float) -> float:
        return max(0.0, min(x, layout.chip.width - block.width))

    def _clamp_y(self, layout: Layout, block: Block, y: float) -> float:
        return max(0.0, min(y, layout.chip.height - block.height))

    def _lock_blocks(self, layout: Layout, action: CommandAction) -> None:
        for block in layout.blocks:
            if block.id in action.targets:
                block.fixed = True

    def _resize_blocks(self, layout: Layout, action: CommandAction) -> None:
        dw = action.params.get("delta_width", 0)
        dh = action.params.get("delta_height", 0)
        for block in layout.blocks:
            if block.id in action.targets and not block.fixed:
                block.width = max(10, block.width + dw)
                block.height = max(10, block.height + dh)

    def _update_property(self, layout: Layout, action: CommandAction) -> None:
        prop = action.params.get("property", "")
        value = action.params.get("value")
        for block in layout.blocks:
            if block.id in action.targets and hasattr(block, prop):
                setattr(block, prop, value)

    def _timing_optimize(self, layout: Layout, targets: list[str]) -> None:
        blocks_map = {b.id: b for b in layout.blocks}
        processed: set[str] = set()

        for net in sorted(layout.nets, key=lambda n: n.criticality, reverse=True):
            if net.criticality < 0.6:
                continue
            group = [net.source] + net.sinks
            group = [g for g in group if g in blocks_map and g in targets]
            if len(group) < 2:
                continue

            cx = sum(blocks_map[g].x + blocks_map[g].width / 2 for g in group) / len(group)
            cy = sum(blocks_map[g].y + blocks_map[g].height / 2 for g in group) / len(group)

            for gid in group:
                if gid in processed or blocks_map[gid].fixed:
                    continue
                block = blocks_map[gid]
                bcx = block.x + block.width / 2
                bcy = block.y + block.height / 2
                block.x += (cx - bcx) * 0.25
                block.y += (cy - bcy) * 0.25
                processed.add(gid)

    def _spread_blocks(self, layout: Layout, targets: list[str], factor: float) -> None:
        if len(targets) < 2:
            return
        blocks_map = {b.id: b for b in layout.blocks}
        cx = sum(blocks_map[t].x + blocks_map[t].width / 2 for t in targets if t in blocks_map)
        cx /= max(1, len(targets))
        cy = sum(blocks_map[t].y + blocks_map[t].height / 2 for t in targets if t in blocks_map)
        cy /= max(1, len(targets))

        for tid in targets:
            if tid not in blocks_map or blocks_map[tid].fixed:
                continue
            block = blocks_map[tid]
            bcx = block.x + block.width / 2
            bcy = block.y + block.height / 2
            dx = bcx - cx
            dy = bcy - cy
            dist = math.hypot(dx, dy) or 1
            spread = (factor - 1) * 40
            block.x += (dx / dist) * spread
            block.y += (dy / dist) * spread

    def _move_toward(self, block: Block, anchor: Block, factor: float) -> None:
        bcx = block.x + block.width / 2
        bcy = block.y + block.height / 2
        acx = anchor.x + anchor.width / 2
        acy = anchor.y + anchor.height / 2
        block.x += (acx - bcx) * factor
        block.y += (acy - bcy) * factor

    def _move_away(self, block: Block, anchor: Block, factor: float) -> None:
        bcx = block.x + block.width / 2
        bcy = block.y + block.height / 2
        acx = anchor.x + anchor.width / 2
        acy = anchor.y + anchor.height / 2
        dx = bcx - acx
        dy = bcy - acy
        dist = math.hypot(dx, dy) or 1
        block.x += (dx / dist) * factor
        block.y += (dy / dist) * factor

    def _find_block(self, layout: Layout, block_id: str) -> Block | None:
        for block in layout.blocks:
            if block.id == block_id:
                return block
        return None
