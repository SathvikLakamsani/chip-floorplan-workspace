"""Natural-language command parser.

Hybrid design:
1. Rule-based (deterministic, instant, no API key) handles common commands and
   robust phrasing variants (overlap fixes, overlay show/hide, explain queries,
   keepouts, spacing, optimization objectives).
2. If no rule matches AND an LLM provider is configured, fall back to the LLM
   parser for open-ended / broad instructions.
3. If neither applies, return a helpful "could not parse" message.

Every command returns proposed actions + a preview + an explanation + expected
metric impact, gated behind Apply/Cancel in the UI. Overlay and explain
commands are side-effect-free (no layout mutation).
"""

from __future__ import annotations

import copy
import re

from app.models.layout import (
    ActionType,
    Block,
    BlockType,
    CommandAction,
    CommandRequest,
    CommandResponse,
    Layout,
)
from app.services.analysis_engine import AnalysisEngine
from app.services.layout_operations import LayoutOperations
from app.services.llm_parser import LLMCommandParser, LLMError

# Overlay keywords -> overlay id understood by the frontend.
_OVERLAY_KEYWORDS = {
    "congestion": "congestion",
    "congested": "congestion",
    "heatmap": "congestion",
    "timing": "timing",
    "path": "timing",
    "paths": "timing",
    "power": "power",
    "thermal": "power",
    "grid": "powerGrid",
    "straps": "powerGrid",
    "pin": "pins",
    "pins": "pins",
    "net": "nets",
    "nets": "nets",
    "wire": "nets",
    "row": "rows",
    "rows": "rows",
    "halo": "halos",
    "halos": "halos",
    "keepout": "halos",
}


class CommandParser:
    """Rule-based parser with an optional LLM fallback."""

    def __init__(self) -> None:
        self._engine = AnalysisEngine()
        self._ops = LayoutOperations()
        self._llm = LLMCommandParser()

    # ------------------------------------------------------------------
    def parse(self, request: CommandRequest) -> CommandResponse:
        command = request.command.strip().lower()
        layout = request.layout

        rule_result = self._parse_rules(command, layout)
        if rule_result is not None:
            return rule_result

        if self._llm.is_configured():
            try:
                actions, explanation = self._llm.parse(request.command, layout)
                return self._build_response(layout, actions, explanation, source="llm")
            except LLMError as exc:
                return CommandResponse(
                    actions=[],
                    explanation=f"Could not interpret '{request.command}'. {exc}",
                    source="none",
                )

        return CommandResponse(
            actions=[],
            explanation=(
                f"Could not parse command: '{request.command}'. Try: 'make sure "
                "nothing overlaps', 'move SRAM closer to compute', 'lock the PLL', "
                "'add keepout around PLL', 'show congestion', 'optimize for timing', "
                "'explain why WNS is negative', or 'generate three candidate layouts'."
            ),
            source="none",
        )

    # ------------------------------------------------------------------
    # Rule matching (order matters: most specific first)
    # ------------------------------------------------------------------
    def _parse_rules(self, command: str, layout: Layout) -> CommandResponse | None:
        # --- Explain / why questions (no mutation) ---------------------
        if self._matches(command, r"\b(why|explain|what should|what would|how do i)\b"):
            explanation = self._engine.explain_topic(
                layout, self._metrics(layout), command
            )
            return CommandResponse(actions=[], explanation=explanation, source="rule")

        # --- Overlay show/hide (no mutation) ---------------------------
        overlay_resp = self._parse_overlay(command)
        if overlay_resp is not None:
            return overlay_resp

        # --- Separate specific pair: "separate X and Y" ----------------
        pair = self._parse_separate_pair(command, layout)
        if pair is not None:
            return self._build_response(layout, *pair, source="rule")

        # --- Overlap / spacing / not touching --------------------------
        if self._matches(
            command,
            r"no\w*\s+overlap|overlap|not?\s+touch|touching|spread|declutter"
            r"|separate|spacing|space out|breathing room|increase spacing",
        ):
            return self._build_response(layout, *self._separate_all(layout), source="rule")

        # --- Keepout ---------------------------------------------------
        if self._matches(command, r"keepout|keep-out|keep out|halo|noise"):
            actions, expl = self._add_keepout(command, layout)
            if actions:
                return self._build_response(layout, actions, expl, source="rule")

        # --- SRAM closer to compute ------------------------------------
        if self._matches(command, r"sram.*clos(er|e).*compute|move sram.*compute"):
            return self._build_response(layout, *self._sram_closer_to_compute(layout), source="rule")

        # --- Lock / unlock --------------------------------------------
        if self._matches(command, r"lock.*pll|fix.*pll"):
            return self._build_response(layout, *self._lock_pll(layout), source="rule")
        if self._matches(command, r"\bunlock\b|\bunfix\b|\bunpin\b"):
            actions, expl = self._unlock(command, layout)
            if actions:
                return self._build_response(layout, actions, expl, source="rule")
        if self._matches(command, r"\block\b|\bfix\b|\bpin\b"):
            actions, expl = self._lock(command, layout)
            if actions:
                return self._build_response(layout, actions, expl, source="rule")

        # --- Optimize objectives --------------------------------------
        if self._matches(command, r"optimi[sz]e.*congestion|reduce.*congestion|fix.*congestion|less.*congestion"):
            return self._build_response(layout, *self._reduce_congestion(layout), source="rule")
        if self._matches(command, r"optimi[sz]e.*timing|improve.*timing|fix.*timing|optimi[sz]e for timing"):
            return self._build_response(layout, *self._optimize_timing(layout), source="rule")

        # --- Candidates ------------------------------------------------
        if self._matches(command, r"generate.*candidate|create.*candidate|candidate layout|compare.*layout|explore"):
            return self._build_response(layout, *self._generate_candidates_action(layout), source="rule")

        return None

    # ------------------------------------------------------------------
    # Overlay parsing
    # ------------------------------------------------------------------
    def _parse_overlay(self, command: str) -> CommandResponse | None:
        show = bool(re.search(r"\b(show|display|turn on|enable|reveal)\b", command))
        hide = bool(re.search(r"\b(hide|turn off|disable|remove)\b", command))
        if not (show or hide):
            return None
        overlays: dict[str, bool] = {}
        for kw, oid in _OVERLAY_KEYWORDS.items():
            if re.search(rf"\b{kw}\b", command):
                overlays[oid] = show and not hide
        if not overlays:
            return None
        names = ", ".join(sorted(set(overlays)))
        verb = "Showing" if show and not hide else "Hiding"
        return CommandResponse(
            actions=[],
            overlays=overlays,
            explanation=f"{verb} overlay(s): {names}.",
            source="rule",
        )

    # ------------------------------------------------------------------
    # Separate a specific pair of blocks
    # ------------------------------------------------------------------
    def _parse_separate_pair(
        self, command: str, layout: Layout
    ) -> tuple[list[CommandAction], str] | None:
        if not re.search(r"\bseparate\b|\bmove apart\b|\bpull apart\b", command):
            return None
        m = re.search(r"(?:separate|move apart|pull apart)\s+(.+?)\s+(?:and|from|&)\s+(.+)", command)
        if not m:
            return None
        a = self._find_block_id(layout, m.group(1))
        b = self._find_block_id(layout, m.group(2))
        targets = [t for t in (a, b) if t]
        if len(targets) < 2:
            return None
        return (
            [
                CommandAction(
                    type=ActionType.MOVE_BLOCKS,
                    targets=targets,
                    reason="Push the two blocks apart until they no longer overlap.",
                    params={"mode": "separate", "margin": 20.0},
                )
            ],
            f"Separate {targets[0]} and {targets[1]} so they no longer overlap.",
        )

    def _separate_all(self, layout: Layout) -> tuple[list[CommandAction], str]:
        movable = [b.id for b in layout.blocks if not b.fixed]
        return (
            [
                CommandAction(
                    type=ActionType.MOVE_BLOCKS,
                    targets=movable,
                    reason="Resolve overlaps: push blocks apart until none touch, leaving a spacing margin.",
                    params={"mode": "separate", "margin": 15.0},
                )
            ],
            "Separate all movable blocks so none overlap or touch, keeping a spacing margin.",
        )

    # ------------------------------------------------------------------
    # Keepout / lock / unlock
    # ------------------------------------------------------------------
    def _add_keepout(self, command: str, layout: Layout) -> tuple[list[CommandAction], str]:
        target = self._extract_target(command, layout)
        if not target:
            return [], ""
        return (
            [
                CommandAction(
                    type=ActionType.ADD_KEEPOUT,
                    targets=[target],
                    reason=f"Add a keepout/halo margin around {target} (noise-sensitive or hard macro).",
                    params={"margin": 25.0},
                )
            ],
            f"Add a keepout margin around {target}.",
        )

    def _lock(self, command: str, layout: Layout) -> tuple[list[CommandAction], str]:
        target = self._extract_target(command, layout)
        if not target:
            return [], ""
        return (
            [
                CommandAction(
                    type=ActionType.LOCK_BLOCKS,
                    targets=[target],
                    reason=f"Lock {target} so it cannot move during optimization.",
                )
            ],
            f"Lock {target} in place.",
        )

    def _unlock(self, command: str, layout: Layout) -> tuple[list[CommandAction], str]:
        target = self._extract_target(command, layout)
        if not target:
            return [], ""
        return (
            [
                CommandAction(
                    type=ActionType.UNLOCK_BLOCKS,
                    targets=[target],
                    reason=f"Unlock {target} so it can be moved.",
                )
            ],
            f"Unlock {target}.",
        )

    # ------------------------------------------------------------------
    # Response builder
    # ------------------------------------------------------------------
    def _build_response(
        self,
        layout: Layout,
        actions: list[CommandAction],
        explanation: str,
        source: str,
    ) -> CommandResponse:
        preview_layout = None
        expected_delta: dict[str, float] = {}

        applyable = [
            a
            for a in actions
            if (a.type if isinstance(a.type, str) else a.type.value)
            != ActionType.GENERATE_CANDIDATES.value
        ]
        if applyable:
            preview_layout = self._ops.apply_actions(copy.deepcopy(layout), actions)
            baseline_metrics = self._metrics(layout)
            preview_metrics = preview_layout.metrics or self._engine.analyze(preview_layout)
            expected_delta = self._delta(baseline_metrics, preview_metrics)

        return CommandResponse(
            actions=actions,
            preview_layout=preview_layout,
            expected_metric_delta=expected_delta,
            explanation=explanation,
            source=source,
        )

    def _delta(self, base, prev) -> dict[str, float]:
        return {
            "wns": round(prev.wns - base.wns, 3),
            "tns": round(prev.tns - base.tns, 3),
            "wire_length": round(prev.wire_length - base.wire_length, 1),
            "congestion_score": round(prev.congestion_score - base.congestion_score, 3),
            "area_utilization": round(prev.area_utilization - base.area_utilization, 3),
            "power_estimate": round(prev.power_estimate - base.power_estimate, 2),
            "drc_count": prev.drc_count - base.drc_count,
        }

    def _metrics(self, layout: Layout):
        return layout.metrics or self._engine.analyze(layout)

    # ------------------------------------------------------------------
    # Existing rule handlers
    # ------------------------------------------------------------------
    def _sram_closer_to_compute(self, layout: Layout) -> tuple[list[CommandAction], str]:
        compute = self._compute_block(layout)
        sram_blocks = self._sram_blocks(layout)
        if not compute or not sram_blocks:
            return [], "Could not find compute array or SRAM blocks."
        targets = [b.id for b in sram_blocks]
        return (
            [
                CommandAction(
                    type=ActionType.MOVE_BLOCKS,
                    targets=targets,
                    reason="Move SRAM banks closer to compute array to reduce critical wire length.",
                    params={"anchor": compute.id, "factor": 0.35},
                )
            ],
            "Move SRAM blocks closer to the compute array to reduce wire length on critical memory paths.",
        )

    def _lock_pll(self, layout: Layout) -> tuple[list[CommandAction], str]:
        pll_blocks = [
            b.id for b in layout.blocks if self._type(b) in ("pll", "clock") or "pll" in b.id
        ]
        if not pll_blocks:
            return [], "No PLL block found in layout."
        return (
            [
                CommandAction(
                    type=ActionType.LOCK_BLOCKS,
                    targets=pll_blocks,
                    reason="Lock PLL block — clock source should remain fixed during optimization.",
                )
            ],
            "Lock the PLL block to prevent accidental movement of the clock source.",
        )

    def _optimize_timing(self, layout: Layout) -> tuple[list[CommandAction], str]:
        high_crit_nets = [n for n in layout.nets if n.criticality >= 0.7]
        targets: set[str] = set()
        for net in high_crit_nets:
            targets.add(net.source)
            targets.update(net.sinks)
        movable = [t for t in targets if not self._is_fixed(layout, t)]
        return (
            [
                CommandAction(
                    type=ActionType.MOVE_BLOCKS,
                    targets=movable,
                    reason="Reposition high-criticality connected blocks to minimize timing path length.",
                    params={"mode": "timing_optimize"},
                )
            ],
            "Optimize layout for timing by moving high-criticality connected blocks closer together.",
        )

    def _reduce_congestion(self, layout: Layout) -> tuple[list[CommandAction], str]:
        dense_blocks = self._find_dense_region_blocks(layout)
        return (
            [
                CommandAction(
                    type=ActionType.MOVE_BLOCKS,
                    targets=dense_blocks,
                    reason="Increase spacing between heavily connected blocks to reduce routing congestion.",
                    params={"mode": "spread", "factor": 1.3},
                )
            ],
            "Reduce congestion by spreading apart blocks in the densest connected region.",
        )

    def _generate_candidates_action(self, layout: Layout) -> tuple[list[CommandAction], str]:
        return (
            [
                CommandAction(
                    type=ActionType.GENERATE_CANDIDATES,
                    targets=[],
                    reason="Generate multiple layout candidates for comparison.",
                    params={"count": 3},
                )
            ],
            "Generate 3 candidate layouts optimized for timing, congestion, and area.",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _matches(self, command: str, pattern: str) -> bool:
        return bool(re.search(pattern, command))

    def _type(self, b: Block) -> str:
        return b.type if isinstance(b.type, str) else b.type.value

    def _extract_target(self, command: str, layout: Layout) -> str | None:
        # Try each block; pick the one whose name/id best appears in the command.
        best: str | None = None
        best_len = 0
        for block in layout.blocks:
            for token in (block.id, block.name):
                frag = token.lower()
                if frag in command and len(frag) > best_len:
                    best = block.id
                    best_len = len(frag)
        if best:
            return best
        # Fallback: match simplified fragments after keywords.
        m = re.search(r"(?:around|the|of|for)\s+([a-z0-9_ ]+)$", command)
        if m:
            return self._find_block_id(layout, m.group(1))
        return None

    def _find_block_id(self, layout: Layout, name_fragment: str) -> str | None:
        fragment = re.sub(r"[^a-z0-9]", "", name_fragment.lower())
        if not fragment:
            return None
        for block in layout.blocks:
            if fragment in re.sub(r"[^a-z0-9]", "", block.id.lower()):
                return block.id
            if fragment in re.sub(r"[^a-z0-9]", "", block.name.lower()):
                return block.id
        # Handle "sram 3" -> "sram_3"
        m = re.search(r"([a-z]+)\s*(\d+)", name_fragment.lower())
        if m:
            candidate = f"{m.group(1)}_{m.group(2)}"
            for block in layout.blocks:
                if block.id.lower() == candidate:
                    return block.id
        return None

    def _sram_blocks(self, layout: Layout) -> list[Block]:
        return [b for b in layout.blocks if self._type(b) in ("sram", "memory")]

    def _compute_block(self, layout: Layout) -> Block | None:
        for block in layout.blocks:
            if block.id == "compute_array" or self._type(block) == "compute":
                return block
        return None

    def _is_fixed(self, layout: Layout, block_id: str) -> bool:
        for block in layout.blocks:
            if block.id == block_id:
                return block.fixed
        return False

    def _find_dense_region_blocks(self, layout: Layout) -> list[str]:
        chip = layout.chip
        mid_x = chip.width / 2
        mid_y = chip.height / 2
        candidates = [
            b.id
            for b in layout.blocks
            if (b.x + b.width / 2) > mid_x and (b.y + b.height / 2) > mid_y and not b.fixed
        ]
        if not candidates:
            return [b.id for b in layout.blocks if not b.fixed][:3]
        return candidates
