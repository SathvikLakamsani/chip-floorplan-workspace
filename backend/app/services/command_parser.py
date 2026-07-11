"""Natural-language command parser.

Hybrid design:
1. Rule-based (deterministic, instant, no API key) handles the common commands.
2. If no rule matches AND an LLM provider is configured, fall back to the LLM
   parser for open-ended / broad instructions.
3. If neither applies, return a helpful "could not parse" message.

The LLM path is optional — with no API key the app behaves exactly as before.
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


class CommandParser:
    """Rule-based parser with an optional LLM fallback."""

    def __init__(self) -> None:
        self._engine = AnalysisEngine()
        self._ops = LayoutOperations()
        self._llm = LLMCommandParser()

    def parse(self, request: CommandRequest) -> CommandResponse:
        command = request.command.strip().lower()
        layout = request.layout

        # 1. Try the deterministic rule-based parser first.
        rule_result = self._parse_rules(command, layout)
        if rule_result is not None:
            actions, explanation = rule_result
            return self._build_response(layout, actions, explanation, source="rule")

        # 2. Fall back to the LLM for open-ended commands, if configured.
        if self._llm.is_configured():
            try:
                actions, explanation = self._llm.parse(request.command, layout)
                return self._build_response(layout, actions, explanation, source="llm")
            except LLMError as exc:
                return CommandResponse(
                    actions=[],
                    explanation=(
                        f"Could not interpret '{request.command}'. {exc}"
                    ),
                    source="none",
                )

        # 3. No rule matched and no LLM available.
        return CommandResponse(
            actions=[],
            explanation=(
                f"Could not parse command: '{request.command}'. "
                "Try: 'move SRAM closer to compute', 'lock the PLL', "
                "'optimize for timing', 'reduce congestion', "
                "'generate three candidate layouts'. "
                "For open-ended commands, set ANTHROPIC_API_KEY or OPENAI_API_KEY "
                "to enable the AI parser."
            ),
            source="none",
        )

    def _parse_rules(
        self, command: str, layout: Layout
    ) -> tuple[list[CommandAction], str] | None:
        """Return (actions, explanation) if a rule matches, else None."""
        if self._matches(command, r"sram.*clos(er|e).*compute|move sram.*compute"):
            return self._sram_closer_to_compute(layout)

        if self._matches(command, r"lock.*pll|fix.*pll"):
            return self._lock_pll(layout)

        if self._matches(command, r"optimi[sz]e.*timing|improve.*timing"):
            return self._optimize_timing(layout)

        if self._matches(command, r"reduce.*congestion|fix.*congestion|less.*congestion"):
            return self._reduce_congestion(layout)

        if self._matches(command, r"generate.*candidate|create.*candidate|candidate layout"):
            return self._generate_candidates_action(layout)

        if self._matches(command, r"lock\s+(\w+)"):
            block_id = re.search(r"lock\s+(\w+)", command)
            if block_id:
                target = self._find_block_id(layout, block_id.group(1))
                if target:
                    return (
                        [
                            CommandAction(
                                type=ActionType.LOCK_BLOCKS,
                                targets=[target],
                                reason=f"Lock block '{target}' to prevent movement.",
                            )
                        ],
                        f"Lock {target} in place.",
                    )

        return None

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
            baseline_metrics = self._engine.analyze(layout)
            preview_metrics = self._engine.analyze(preview_layout)
            expected_delta = {
                "wns": round(preview_metrics.wns - baseline_metrics.wns, 3),
                "tns": round(preview_metrics.tns - baseline_metrics.tns, 3),
                "wire_length": round(
                    preview_metrics.wire_length - baseline_metrics.wire_length, 1
                ),
                "congestion_score": round(
                    preview_metrics.congestion_score - baseline_metrics.congestion_score, 3
                ),
                "area_utilization": round(
                    preview_metrics.area_utilization - baseline_metrics.area_utilization, 3
                ),
                "power_estimate": round(
                    preview_metrics.power_estimate - baseline_metrics.power_estimate, 2
                ),
            }
            preview_layout.metrics = preview_metrics

        return CommandResponse(
            actions=actions,
            preview_layout=preview_layout,
            expected_metric_delta=expected_delta,
            explanation=explanation,
            source=source,
        )

    def _matches(self, command: str, pattern: str) -> bool:
        return bool(re.search(pattern, command))

    def _find_block_id(self, layout: Layout, name_fragment: str) -> str | None:
        fragment = name_fragment.lower().replace("_", "")
        for block in layout.blocks:
            if fragment in block.id.lower().replace("_", ""):
                return block.id
            if fragment in block.name.lower().replace("_", ""):
                return block.id
        return None

    def _sram_blocks(self, layout: Layout) -> list[Block]:
        return [b for b in layout.blocks if b.type == BlockType.SRAM or b.type == "sram"]

    def _compute_block(self, layout: Layout) -> Block | None:
        for block in layout.blocks:
            if block.id == "compute_array" or block.type in (BlockType.COMPUTE, "compute"):
                return block
        return None

    def _sram_closer_to_compute(
        self, layout: Layout
    ) -> tuple[list[CommandAction], str]:
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
            b.id for b in layout.blocks if b.type in (BlockType.PLL, "pll") or "pll" in b.id
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
                    params={"mode": "spread", "factor": 1.2},
                )
            ],
            "Reduce congestion by spreading apart blocks in the densest connected region.",
        )

    def _generate_candidates_action(
        self, layout: Layout
    ) -> tuple[list[CommandAction], str]:
        return (
            [
                CommandAction(
                    type=ActionType.GENERATE_CANDIDATES,
                    targets=[],
                    reason="Generate multiple layout candidates for comparison.",
                    params={"count": 3},
                )
            ],
            "Generate 3 candidate layouts optimized for different objectives (timing, congestion, area).",
        )

    def _is_fixed(self, layout: Layout, block_id: str) -> bool:
        for block in layout.blocks:
            if block.id == block_id:
                return block.fixed
        return False

    def _find_dense_region_blocks(self, layout: Layout) -> list[str]:
        """Find blocks in the top-right quadrant with most net traffic."""
        chip = layout.chip
        mid_x = chip.width / 2
        mid_y = chip.height / 2
        candidates = [
            b.id
            for b in layout.blocks
            if (b.x + b.width / 2) > mid_x and (b.y + b.height / 2) > mid_y
        ]
        if not candidates:
            return [b.id for b in layout.blocks if not b.fixed][:3]
        return candidates
