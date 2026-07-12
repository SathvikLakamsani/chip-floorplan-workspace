"""Mock analysis engine for layout quality metrics.

Computes approximate QoR metrics (timing, wire length, congestion, utilization,
power, DRC) and derives spatial overlays (timing paths, congestion regions,
power-density regions) so the UI can render an EDA-report-like experience
without a real OpenROAD run.
"""

from __future__ import annotations

import math

from app.models.layout import (
    Block,
    CongestionRegion,
    Layout,
    Metrics,
    Net,
    PowerRegion,
    TimingPath,
)
from app.services.validation import ValidationEngine


class AnalysisEngine:
    """Compute approximate layout metrics for UX feedback."""

    def __init__(self) -> None:
        self._validator = ValidationEngine()

    # ------------------------------------------------------------------
    # Top-level analysis
    # ------------------------------------------------------------------
    def analyze(self, layout: Layout) -> Metrics:
        wire_length = self._compute_wire_length(layout)
        congestion = self._estimate_congestion(layout)
        utilization = self._estimate_utilization(layout)
        power = sum(b.power for b in layout.blocks)

        paths = self.derive_timing_paths(layout)
        slacks = [p.slack for p in paths]
        wns = round(min(slacks), 3) if slacks else 0.0
        tns = round(sum(s for s in slacks if s < 0), 3)
        violating = sum(1 for s in slacks if s < 0)

        metrics = Metrics(
            wns=wns,
            tns=tns,
            violating_paths=violating,
            wire_length=round(wire_length, 1),
            congestion_score=round(congestion, 3),
            area_utilization=round(utilization, 3),
            power_estimate=round(power, 2),
        )
        # DRC count folds in the geometry + metric checks.
        report = self._validator.check(layout, metrics)
        metrics.drc_count = len(report.violations)
        return metrics

    def enrich(self, layout: Layout) -> Layout:
        """Populate derived overlays (timing paths / congestion / power) in place.

        Existing hand-authored overlays are preserved; only empty ones are filled.
        """
        if not layout.timing_paths:
            layout.timing_paths = self.derive_timing_paths(layout)[:5]
        if not layout.congestion_regions:
            layout.congestion_regions = self.derive_congestion_regions(layout)
        if not layout.power_regions:
            layout.power_regions = self.derive_power_regions(layout)
        return layout

    # ------------------------------------------------------------------
    # Explanations
    # ------------------------------------------------------------------
    def explain(self, layout: Layout, metrics: Metrics) -> list[str]:
        explanations: list[str] = []

        if metrics.wns < 0:
            explanations.append(
                f"Negative WNS ({metrics.wns} ns) across {metrics.violating_paths} "
                "violating path(s) — critical connections are physically too long."
            )
        else:
            explanations.append(f"WNS is {metrics.wns} ns — timing margin is positive.")

        high_crit_nets = [n for n in layout.nets if n.criticality >= 0.8]
        if high_crit_nets:
            avg_dist = self._avg_critical_net_distance(layout, high_crit_nets)
            explanations.append(
                f"{len(high_crit_nets)} high-criticality nets with avg source-sink "
                f"distance {avg_dist:.0f} μm — shorter distances improve timing."
            )

        if metrics.congestion_score > 0.7:
            explanations.append(
                f"Congestion score {metrics.congestion_score:.2f} is high — "
                "consider increasing spacing between densely connected blocks."
            )

        if metrics.drc_count:
            explanations.append(
                f"{metrics.drc_count} legality/DRC issue(s) detected — see the "
                "DRC / Legality panel."
            )

        explanations.append(
            f"Area utilization {metrics.area_utilization:.0%} across "
            f"{len(layout.blocks)} blocks; estimated wire length "
            f"{metrics.wire_length:.0f} μm."
        )
        return explanations

    def explain_topic(self, layout: Layout, metrics: Metrics, topic: str) -> str:
        """Answer targeted 'why' questions from the command bar."""
        t = topic.lower()
        if "wns" in t or "timing" in t or "slack" in t:
            paths = self.derive_timing_paths(layout)
            worst = paths[0] if paths else None
            if worst and worst.slack < 0:
                return (
                    f"WNS is {metrics.wns} ns because the worst path "
                    f"{worst.startpoint} → {worst.endpoint} spans {worst.distance:.0f} μm "
                    f"(slack {worst.slack} ns). {worst.explanation} Move these blocks "
                    "closer or reduce fanout to recover slack."
                )
            return f"WNS is {metrics.wns} ns — timing currently meets its target."
        if "congest" in t:
            regions = self.derive_congestion_regions(layout)
            if regions:
                r = max(regions, key=lambda x: x.score)
                return (
                    f"The region near ({r.x:.0f}, {r.y:.0f}) has congestion "
                    f"{r.score:.2f}: {r.reason} Try spreading these blocks apart "
                    "or widening routing channels."
                )
            return "No significant congestion hotspots detected."
        if "power" in t or "thermal" in t:
            regions = self.derive_power_regions(layout)
            if regions:
                r = max(regions, key=lambda x: x.density)
                return (
                    f"Highest power density is {r.density:.2f} W/μm² near "
                    f"({r.x:.0f}, {r.y:.0f}): {r.reason} Consider spacing high-power "
                    "blocks apart to spread heat."
                )
            return "Power density is evenly distributed."
        if "change" in t or "improve" in t or "should" in t:
            return self._suggest_actions(layout, metrics)
        return (
            "I can explain WNS/timing, congestion, power density, or suggest what to "
            "change. Try 'explain why WNS is negative' or 'what should I change'."
        )

    def suggested_actions(self, layout: Layout, metrics: Metrics) -> list[str]:
        actions: list[str] = []
        if metrics.wns < 0:
            actions.append(
                "Move timing-critical connected blocks (e.g. SRAM banks near the "
                "compute array) closer together to recover WNS."
            )
        if metrics.congestion_score > 0.7:
            actions.append(
                "Spread apart blocks in the densest region to reduce congestion."
            )
        if metrics.area_utilization > 0.8:
            actions.append("Enlarge the core area — utilization is high.")
        if metrics.drc_count:
            actions.append("Resolve overlaps/halo violations in the DRC panel.")
        if not actions:
            actions.append("Layout looks healthy — try generating candidates to explore.")
        return actions

    def _suggest_actions(self, layout: Layout, metrics: Metrics) -> str:
        return " ".join(f"{i + 1}. {a}" for i, a in enumerate(self.suggested_actions(layout, metrics)))

    # ------------------------------------------------------------------
    # Derived overlays
    # ------------------------------------------------------------------
    def derive_timing_paths(self, layout: Layout) -> list[TimingPath]:
        blocks = self._block_map(layout)
        paths: list[TimingPath] = []
        idx = 0
        for net in sorted(layout.nets, key=lambda n: n.criticality, reverse=True):
            if net.source not in blocks:
                continue
            sx, sy = self._block_center(blocks[net.source])
            for sink in net.sinks:
                if sink not in blocks:
                    continue
                tx, ty = self._block_center(blocks[sink])
                dist = math.hypot(tx - sx, ty - sy)
                # Pseudo-slack: longer + more critical => more negative.
                slack = round(0.12 - dist / 3500.0 - (net.criticality - 0.5) * 0.18, 3)
                idx += 1
                paths.append(
                    TimingPath(
                        id=f"path_{idx}",
                        startpoint=net.source,
                        endpoint=sink,
                        slack=slack,
                        distance=round(dist, 1),
                        criticality=net.criticality,
                        clock=blocks[net.source].clock_domain or "core_clk",
                        explanation=(
                            f"{blocks[net.source].name} and {blocks[sink].name} are "
                            f"connected by a criticality-{net.criticality:.2f} net and "
                            f"are {dist:.0f} μm apart."
                        ),
                    )
                )
        paths.sort(key=lambda p: p.slack)
        return paths

    def derive_congestion_regions(self, layout: Layout) -> list[CongestionRegion]:
        chip = layout.chip
        grid = 100.0
        cols = max(1, int(chip.width / grid))
        rows = max(1, int(chip.height / grid))
        acc = [[0.0] * cols for _ in range(rows)]
        blocks = self._block_map(layout)

        for net in layout.nets:
            if net.source not in blocks:
                continue
            sx, sy = self._block_center(blocks[net.source])
            for sink in net.sinks:
                if sink not in blocks:
                    continue
                tx, ty = self._block_center(blocks[sink])
                steps = 12
                for i in range(steps + 1):
                    t = i / steps
                    px = sx + t * (tx - sx)
                    py = sy + t * (ty - sy)
                    cx = min(int(px / grid), cols - 1)
                    cy = min(int(py / grid), rows - 1)
                    acc[cy][cx] += net.traffic * (net.width / 64.0)

        peak = max((max(r) for r in acc), default=0.0) or 1.0
        regions: list[CongestionRegion] = []
        for cy in range(rows):
            for cx in range(cols):
                score = acc[cy][cx] / peak
                if score >= 0.55:
                    regions.append(
                        CongestionRegion(
                            x=cx * grid,
                            y=cy * grid,
                            width=grid,
                            height=grid,
                            score=round(score, 3),
                            reason="Multiple high-traffic nets cross this channel.",
                        )
                    )
        regions.sort(key=lambda r: r.score, reverse=True)
        return regions[:8]

    def derive_power_regions(self, layout: Layout) -> list[PowerRegion]:
        densities = [b.power_density for b in layout.blocks if b.area > 0]
        peak = max(densities, default=0.0) or 1.0
        regions: list[PowerRegion] = []
        for b in layout.blocks:
            if b.area <= 0 or b.power <= 0:
                continue
            d = b.power_density / peak
            if d >= 0.4:
                regions.append(
                    PowerRegion(
                        x=b.x,
                        y=b.y,
                        width=b.width,
                        height=b.height,
                        density=round(d, 3),
                        reason=f"{b.name} draws {b.power:.2f} W over {b.area:.0f} μm².",
                    )
                )
        regions.sort(key=lambda r: r.density, reverse=True)
        return regions[:8]

    # ------------------------------------------------------------------
    # Metric primitives
    # ------------------------------------------------------------------
    def _block_center(self, block: Block) -> tuple[float, float]:
        return (block.x + block.width / 2, block.y + block.height / 2)

    def _block_map(self, layout: Layout) -> dict[str, Block]:
        return {b.id: b for b in layout.blocks}

    def _compute_wire_length(self, layout: Layout) -> float:
        blocks = self._block_map(layout)
        total = 0.0
        for net in layout.nets:
            if net.source not in blocks:
                continue
            sx, sy = self._block_center(blocks[net.source])
            weight = net.criticality * net.traffic * net.width / 64
            for sink in net.sinks:
                if sink not in blocks:
                    continue
                tx, ty = self._block_center(blocks[sink])
                dist = math.hypot(tx - sx, ty - sy)
                total += dist * max(weight, 0.1)
        return total

    def _estimate_congestion(self, layout: Layout) -> float:
        regions = self.derive_congestion_regions(layout)
        if not regions:
            return 0.0
        # Blend peak and average of hot regions.
        peak = regions[0].score
        avg = sum(r.score for r in regions) / len(regions)
        return min(1.0, 0.6 * peak + 0.4 * avg)

    def _estimate_utilization(self, layout: Layout) -> float:
        core = layout.chip.core
        area = (core.width * core.height) if core else (layout.chip.width * layout.chip.height)
        if area <= 0:
            return 0.0
        block_area = sum(b.width * b.height for b in layout.blocks if not self._is_io(b))
        return min(1.0, block_area / area)

    def _is_io(self, b: Block) -> bool:
        t = b.type if isinstance(b.type, str) else b.type.value
        return t == "io"

    def _avg_critical_net_distance(self, layout: Layout, nets: list[Net]) -> float:
        blocks = self._block_map(layout)
        distances: list[float] = []
        for net in nets:
            if net.source not in blocks:
                continue
            sx, sy = self._block_center(blocks[net.source])
            for sink in net.sinks:
                if sink not in blocks:
                    continue
                tx, ty = self._block_center(blocks[sink])
                distances.append(math.hypot(tx - sx, ty - sy))
        return sum(distances) / len(distances) if distances else 0.0
