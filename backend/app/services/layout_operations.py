"""Layout mutation operations applied from structured command actions."""

from __future__ import annotations

import copy
import math
import re

from app.models.layout import (
    ActionType,
    Block,
    CommandAction,
    Constraint,
    Halo,
    Layout,
    Net,
    Rect,
)
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
            elif action_type == ActionType.UNLOCK_BLOCKS.value:
                self._unlock_blocks(result, action)
            elif action_type == ActionType.RESIZE_BLOCKS.value:
                self._resize_blocks(result, action)
            elif action_type == ActionType.UPDATE_PROPERTY.value:
                self._update_property(result, action)
            elif action_type == ActionType.ADD_KEEPOUT.value:
                self._add_keepout(result, action)
            elif action_type == ActionType.ADD_CONSTRAINT.value:
                self._add_constraint(result, action)
            elif action_type == ActionType.ADD_BLOCK.value:
                self._add_block(result, action)
            elif action_type == ActionType.REMOVE_BLOCK.value:
                self._remove_block(result, action)
            elif action_type == ActionType.CLONE_BLOCK.value:
                self._clone_block(result, action)
            elif action_type == ActionType.ADD_NET.value:
                self._add_net(result, action)
            elif action_type == ActionType.REMOVE_NET.value:
                self._remove_net(result, action)
            elif action_type == ActionType.ALIGN_BLOCKS.value:
                self._align_blocks(result, action)
            elif action_type == ActionType.DISTRIBUTE_BLOCKS.value:
                self._distribute_blocks(result, action)
            elif action_type == ActionType.SET_CHIP.value:
                self._set_chip(result, action)
        result.metrics = self._engine.analyze(result)
        self._engine.enrich(result)
        return result

    def generate_candidates(
        self, layout: Layout, count: int = 3
    ) -> list[tuple[Layout, str, str, str]]:
        """Generate candidates with distinct objectives.

        Returns tuples of (layout, objective, explanation, tradeoff).
        """
        candidates: list[tuple[Layout, str, str, str]] = []

        # Candidate A: timing — move SRAM/critical blocks closer to compute.
        timing_layout = copy.deepcopy(layout)
        compute = self._find_block(timing_layout, "compute_array")
        if compute:
            for block in timing_layout.blocks:
                if self._type(block) in ("sram", "memory") and not block.fixed:
                    self._move_toward(block, compute, factor=0.4)
        self._resolve_overlaps(timing_layout)
        timing_layout.metrics = self._engine.analyze(timing_layout)
        self._engine.enrich(timing_layout)
        candidates.append(
            (
                timing_layout,
                "timing",
                "Improves WNS by moving SRAM banks closer to the compute array, "
                "shortening critical memory paths.",
                "Increases local congestion near the compute array.",
            )
        )

        # Candidate B: congestion — open routing channels around the NoC.
        congestion_layout = copy.deepcopy(layout)
        noc = self._find_block(congestion_layout, "noc_router")
        mem_ctrl = self._find_block(congestion_layout, "memory_controller")
        for block in congestion_layout.blocks:
            if block.fixed:
                continue
            if noc and block.id != noc.id:
                self._move_away(block, noc, factor=35)
            if mem_ctrl and block.id != mem_ctrl.id:
                self._move_away(block, mem_ctrl, factor=20)
        self._resolve_overlaps(congestion_layout)
        congestion_layout.metrics = self._engine.analyze(congestion_layout)
        self._engine.enrich(congestion_layout)
        candidates.append(
            (
                congestion_layout,
                "congestion",
                "Opens routing channels by increasing spacing around the NoC router "
                "and memory controller.",
                "Increases total wire length.",
            )
        )

        # Candidate C: compact — pull blocks toward core center.
        area_layout = copy.deepcopy(layout)
        core = area_layout.chip.core
        center_x = (core.x + core.width / 2) if core else layout.chip.width / 2
        center_y = (core.y + core.height / 2) if core else layout.chip.height / 2
        for block in area_layout.blocks:
            if not block.fixed:
                bcx = block.x + block.width / 2
                bcy = block.y + block.height / 2
                block.x += (center_x - bcx) * 0.18
                block.y += (center_y - bcy) * 0.18
        self._resolve_overlaps(area_layout)
        area_layout.metrics = self._engine.analyze(area_layout)
        self._engine.enrich(area_layout)
        candidates.append(
            (
                area_layout,
                "compact",
                "Reduces the area footprint by compacting blocks toward the core center.",
                "Worsens timing and congestion due to tighter packing.",
            )
        )

        return candidates[:count]

    def _resolve_overlaps(self, layout: Layout) -> None:
        movable = [b.id for b in layout.blocks if not b.fixed]
        self._separate_blocks(layout, movable, margin=6.0, iterations=60)

    def _type(self, b: Block) -> str:
        return b.type if isinstance(b.type, str) else b.type.value

    def _move_blocks(self, layout: Layout, action: CommandAction) -> None:
        params = action.params
        mode = params.get("mode", "anchor")

        if mode == "timing_optimize":
            self._timing_optimize(layout, action.targets)
        elif mode in ("separate", "no_overlap", "declutter"):
            self._separate_blocks(
                layout,
                action.targets,
                margin=float(params.get("margin", 15.0) or 15.0),
            )
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
                block.placement_status = "fixed"

    def _unlock_blocks(self, layout: Layout, action: CommandAction) -> None:
        for block in layout.blocks:
            if block.id in action.targets:
                block.fixed = False
                block.placement_status = "placed"

    def _add_keepout(self, layout: Layout, action: CommandAction) -> None:
        margin = float(action.params.get("margin", 20.0) or 20.0)
        for block in layout.blocks:
            if block.id in action.targets:
                block.keepout = True
                block.halo = Halo(left=margin, right=margin, top=margin, bottom=margin)

    def _add_constraint(self, layout: Layout, action: CommandAction) -> None:
        ctype = str(action.params.get("constraint_type", "proximity"))
        desc = action.reason or f"{ctype} constraint"
        layout.constraints.append(
            Constraint(
                id=f"constraint_{len(layout.constraints) + 1}",
                type=ctype,
                description=desc,
                targets=list(action.targets),
                priority=str(action.params.get("priority", "medium")),
                params={k: v for k, v in action.params.items() if k not in ("constraint_type", "priority")},
            )
        )

    # ------------------------------------------------------------------
    # Structural edits (create / remove / duplicate design objects)
    # ------------------------------------------------------------------
    _CLASS_BY_TYPE = {
        "sram": "hard_macro",
        "memory": "memory",
        "pll": "clock",
        "clock": "clock",
        "io": "io",
        "analog": "analog",
        "compute": "soft_logic",
        "noc": "soft_logic",
        "controller": "soft_logic",
        "stdcell": "standard_cell_region",
    }

    def _slug(self, text: str) -> str:
        s = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
        return s or "block"

    def _unique_id(self, existing: set[str], base: str) -> str:
        base = self._slug(base)
        if base not in existing:
            return base
        i = 1
        while f"{base}_{i}" in existing:
            i += 1
        return f"{base}_{i}"

    def _add_block(self, layout: Layout, action: CommandAction) -> None:
        p = action.params
        existing = {b.id for b in layout.blocks}
        name = str(p.get("name") or p.get("id") or "New Block")
        block_id = self._unique_id(existing, str(p.get("id") or name))
        btype = str(p.get("type", "other") or "other")
        cls = str(p.get("class") or p.get("cls") or self._CLASS_BY_TYPE.get(btype, "soft_logic"))
        width = float(p.get("width", 120) or 120)
        height = float(p.get("height", 120) or 120)

        area = layout.chip.core or layout.chip.die
        if p.get("x") is not None:
            x = float(p["x"])
        elif area is not None:
            x = area.x + area.width / 2 - width / 2
        else:
            x = layout.chip.width / 2 - width / 2
        if p.get("y") is not None:
            y = float(p["y"])
        elif area is not None:
            y = area.y + area.height / 2 - height / 2
        else:
            y = layout.chip.height / 2 - height / 2

        block = Block(
            id=block_id,
            name=name,
            type=btype,
            cls=cls,
            x=x,
            y=y,
            width=width,
            height=height,
            fixed=bool(p.get("fixed", False)),
            power=float(p.get("power", 0.0) or 0.0),
            criticality=float(p.get("criticality", 0.5) or 0.5),
            clock_domain=str(p.get("clock_domain", "") or ""),
            voltage_domain=str(p.get("voltage_domain", "") or ""),
        )
        block.x = self._clamp_x(layout, block, block.x)
        block.y = self._clamp_y(layout, block, block.y)
        layout.blocks.append(block)
        # Nudge only the new block so it doesn't land on top of existing blocks.
        if not block.fixed:
            self._separate_blocks(layout, [block_id], margin=10.0, iterations=120)

    def _remove_block(self, layout: Layout, action: CommandAction) -> None:
        ids = set(action.targets)
        if not ids:
            return
        layout.blocks = [b for b in layout.blocks if b.id not in ids]
        kept_nets = []
        for n in layout.nets:
            if n.source in ids:
                continue
            n.sinks = [s for s in n.sinks if s not in ids]
            if not n.sinks:
                continue
            kept_nets.append(n)
        layout.nets = kept_nets
        for c in layout.constraints:
            c.targets = [t for t in c.targets if t not in ids]
        layout.constraints = [c for c in layout.constraints if c.targets]

    def _clone_block(self, layout: Layout, action: CommandAction) -> None:
        p = action.params
        dx = float(p.get("dx", 40) or 40)
        dy = float(p.get("dy", 40) or 40)
        existing = {b.id for b in layout.blocks}
        new_blocks: list[Block] = []
        for b in layout.blocks:
            if b.id not in action.targets:
                continue
            new_name = str(p.get("name") or f"{b.name} copy")
            nid = self._unique_id(existing | {nb.id for nb in new_blocks}, new_name)
            clone = b.model_copy(deep=True)
            clone.id = nid
            clone.name = new_name
            clone.fixed = False
            clone.placement_status = "placed"
            clone.x = self._clamp_x(layout, clone, b.x + dx)
            clone.y = self._clamp_y(layout, clone, b.y + dy)
            new_blocks.append(clone)
        layout.blocks.extend(new_blocks)
        if new_blocks:
            self._separate_blocks(
                layout, [b.id for b in new_blocks], margin=10.0, iterations=120
            )

    def _add_net(self, layout: Layout, action: CommandAction) -> None:
        p = action.params
        block_ids = {b.id for b in layout.blocks}
        source = str(p.get("source", "") or "")
        sinks = [s for s in (p.get("sinks") or []) if s in block_ids]
        # Allow targets as an alternative way to specify [source, *sinks].
        if not source and action.targets:
            source = action.targets[0]
            sinks = sinks or [t for t in action.targets[1:] if t in block_ids]
        if source not in block_ids or not sinks:
            return
        existing = {n.id for n in layout.nets}
        nid = self._unique_id(existing, str(p.get("id") or p.get("name") or f"{source}_net"))
        layout.nets.append(
            Net(
                id=nid,
                name=str(p.get("name") or nid),
                source=source,
                sinks=sinks,
                criticality=float(p.get("criticality", 0.5) or 0.5),
                traffic=float(p.get("traffic", 0.5) or 0.5),
                width=int(p.get("width", 32) or 32),
                type=str(p.get("type", "signal") or "signal"),
            )
        )

    def _remove_net(self, layout: Layout, action: CommandAction) -> None:
        ids = set(action.targets) | set(action.params.get("nets", []) or [])
        if not ids:
            return
        layout.nets = [n for n in layout.nets if n.id not in ids]

    def _align_blocks(self, layout: Layout, action: CommandAction) -> None:
        edge = str(action.params.get("edge", "left"))
        targets = [b for b in layout.blocks if b.id in action.targets and not b.fixed]
        if len(targets) < 2:
            return
        if edge == "left":
            v = min(b.x for b in targets)
            for b in targets:
                b.x = self._clamp_x(layout, b, v)
        elif edge == "right":
            v = max(b.x + b.width for b in targets)
            for b in targets:
                b.x = self._clamp_x(layout, b, v - b.width)
        elif edge == "top":
            v = min(b.y for b in targets)
            for b in targets:
                b.y = self._clamp_y(layout, b, v)
        elif edge == "bottom":
            v = max(b.y + b.height for b in targets)
            for b in targets:
                b.y = self._clamp_y(layout, b, v - b.height)
        elif edge in ("centerx", "center_x", "vcenter"):
            c = sum(b.x + b.width / 2 for b in targets) / len(targets)
            for b in targets:
                b.x = self._clamp_x(layout, b, c - b.width / 2)
        elif edge in ("centery", "center_y", "hcenter"):
            c = sum(b.y + b.height / 2 for b in targets) / len(targets)
            for b in targets:
                b.y = self._clamp_y(layout, b, c - b.height / 2)

    def _distribute_blocks(self, layout: Layout, action: CommandAction) -> None:
        axis = str(action.params.get("axis", "x"))
        targets = [b for b in layout.blocks if b.id in action.targets and not b.fixed]
        if len(targets) < 3:
            return
        if axis == "y":
            targets.sort(key=lambda b: b.y)
            lo, hi = targets[0].y, targets[-1].y
            step = (hi - lo) / (len(targets) - 1)
            for i, b in enumerate(targets):
                b.y = self._clamp_y(layout, b, lo + i * step)
        else:
            targets.sort(key=lambda b: b.x)
            lo, hi = targets[0].x, targets[-1].x
            step = (hi - lo) / (len(targets) - 1)
            for i, b in enumerate(targets):
                b.x = self._clamp_x(layout, b, lo + i * step)

    def _set_chip(self, layout: Layout, action: CommandAction) -> None:
        p = action.params
        chip = layout.chip
        die = chip.die or Rect(x=0, y=0, width=chip.width, height=chip.height)
        if isinstance(p.get("die"), dict):
            d = p["die"]
            die = Rect(
                x=float(d.get("x", die.x)),
                y=float(d.get("y", die.y)),
                width=float(d.get("width", die.width)),
                height=float(d.get("height", die.height)),
            )
        else:
            if p.get("width") is not None:
                die.width = float(p["width"])
            if p.get("height") is not None:
                die.height = float(p["height"])
        chip.die = die
        chip.width = die.width
        chip.height = die.height
        if isinstance(p.get("core"), dict):
            c = p["core"]
            chip.core = Rect(
                x=float(c.get("x", die.x)),
                y=float(c.get("y", die.y)),
                width=float(c.get("width", die.width)),
                height=float(c.get("height", die.height)),
            )
        else:
            m = min(die.width, die.height) * 0.08
            chip.core = Rect(
                x=die.x + m,
                y=die.y + m,
                width=max(0.0, die.width - 2 * m),
                height=max(0.0, die.height - 2 * m),
            )

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
        if prop == "class":
            prop = "cls"
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

    def _separate_blocks(
        self,
        layout: Layout,
        targets: list[str],
        margin: float = 15.0,
        iterations: int = 200,
    ) -> None:
        """Resolve overlaps: push blocks apart until none overlap (plus a margin).

        Iterative pairwise minimum-translation separation. A pair is only
        adjusted if at least one block is a movable target; fixed/non-target
        blocks act as immovable obstacles.
        """
        target_set = set(targets)
        blocks = layout.blocks
        for _ in range(iterations):
            moved = False
            for i in range(len(blocks)):
                for j in range(i + 1, len(blocks)):
                    a, b = blocks[i], blocks[j]
                    a_mv = a.id in target_set and not a.fixed
                    b_mv = b.id in target_set and not b.fixed
                    if not a_mv and not b_mv:
                        continue
                    acx, acy = a.x + a.width / 2, a.y + a.height / 2
                    bcx, bcy = b.x + b.width / 2, b.y + b.height / 2
                    dx, dy = acx - bcx, acy - bcy
                    min_dx = (a.width + b.width) / 2 + margin
                    min_dy = (a.height + b.height) / 2 + margin
                    ox = min_dx - abs(dx)
                    oy = min_dy - abs(dy)
                    if ox <= 0 or oy <= 0:
                        continue
                    if ox < oy:
                        sign = 1.0 if dx > 0 else (-1.0 if dx < 0 else (1.0 if i < j else -1.0))
                        if a_mv and b_mv:
                            a.x = self._clamp_x(layout, a, a.x + sign * ox / 2)
                            b.x = self._clamp_x(layout, b, b.x - sign * ox / 2)
                        elif a_mv:
                            a.x = self._clamp_x(layout, a, a.x + sign * ox)
                        else:
                            b.x = self._clamp_x(layout, b, b.x - sign * ox)
                    else:
                        sign = 1.0 if dy > 0 else (-1.0 if dy < 0 else (1.0 if i < j else -1.0))
                        if a_mv and b_mv:
                            a.y = self._clamp_y(layout, a, a.y + sign * oy / 2)
                            b.y = self._clamp_y(layout, b, b.y - sign * oy / 2)
                        elif a_mv:
                            a.y = self._clamp_y(layout, a, a.y + sign * oy)
                        else:
                            b.y = self._clamp_y(layout, b, b.y - sign * oy)
                    moved = True
            if not moved:
                break

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
