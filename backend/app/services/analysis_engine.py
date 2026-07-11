"""Mock analysis engine for layout quality metrics."""

from __future__ import annotations

import math

from app.models.layout import Block, Layout, Metrics, Net


class AnalysisEngine:
    """Compute approximate layout metrics for UX feedback."""

    def analyze(self, layout: Layout) -> Metrics:
        wire_length = self._compute_wire_length(layout)
        congestion = self._estimate_congestion(layout)
        timing_score = self._estimate_timing_score(layout)
        utilization = self._estimate_utilization(layout)
        power = sum(b.power for b in layout.blocks)

        # Mock WNS/TNS from timing score (lower distance -> better timing)
        wns = round(timing_score - 0.15, 3)
        tns = round(wns * max(1, len([n for n in layout.nets if n.criticality > 0.7])), 3)

        return Metrics(
            wns=wns,
            tns=tns,
            wire_length=round(wire_length, 1),
            congestion_score=round(congestion, 3),
            area_utilization=round(utilization, 3),
            power_estimate=round(power, 2),
        )

    def explain(self, layout: Layout, metrics: Metrics) -> list[str]:
        explanations: list[str] = []

        if metrics.wns < 0:
            explanations.append(
                f"Negative WNS ({metrics.wns} ns) indicates timing violations on critical paths."
            )
        else:
            explanations.append(f"WNS is {metrics.wns} ns — timing margin is positive.")

        high_crit_nets = [n for n in layout.nets if n.criticality >= 0.8]
        if high_crit_nets:
            avg_dist = self._avg_critical_net_distance(layout, high_crit_nets)
            explanations.append(
                f"{len(high_crit_nets)} high-criticality nets with avg source-sink distance "
                f"{avg_dist:.0f} μm — shorter distances improve timing."
            )

        if metrics.congestion_score > 0.7:
            explanations.append(
                f"Congestion score {metrics.congestion_score:.2f} is high — "
                "consider increasing spacing between densely connected blocks."
            )

        explanations.append(
            f"Area utilization {metrics.area_utilization:.0%} across "
            f"{len(layout.blocks)} blocks."
        )
        explanations.append(f"Estimated total wire length: {metrics.wire_length:.0f} μm.")

        return explanations

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

    def _estimate_timing_score(self, layout: Layout) -> float:
        blocks = self._block_map(layout)
        if not layout.nets:
            return 0.0

        weighted_dist = 0.0
        total_weight = 0.0
        for net in layout.nets:
            if net.source not in blocks:
                continue
            sx, sy = self._block_center(blocks[net.source])
            for sink in net.sinks:
                if sink not in blocks:
                    continue
                tx, ty = self._block_center(blocks[sink])
                dist = math.hypot(tx - sx, ty - sy)
                w = net.criticality
                weighted_dist += dist * w
                total_weight += w

        if total_weight == 0:
            return 0.0

        avg_dist = weighted_dist / total_weight
        # Map distance to pseudo-WNS: closer blocks -> better (less negative) WNS
        return round(0.05 - avg_dist / 5000, 3)

    def _estimate_congestion(self, layout: Layout) -> float:
        """Estimate congestion from block density and net crossings in grid cells."""
        chip = layout.chip
        grid_size = 100
        cols = max(1, int(chip.width / grid_size))
        rows = max(1, int(chip.height / grid_size))

        density = [[0.0 for _ in range(cols)] for _ in range(rows)]
        blocks = self._block_map(layout)

        for block in layout.blocks:
            cx = int((block.x + block.width / 2) / grid_size)
            cy = int((block.y + block.height / 2) / grid_size)
            cx = min(cx, cols - 1)
            cy = min(cy, rows - 1)
            area_frac = (block.width * block.height) / (grid_size * grid_size)
            density[cy][cx] += area_frac

        for net in layout.nets:
            if net.source not in blocks:
                continue
            sx, sy = self._block_center(blocks[net.source])
            for sink in net.sinks:
                if sink not in blocks:
                    continue
                tx, ty = self._block_center(blocks[sink])
                steps = 10
                for i in range(steps + 1):
                    t = i / steps
                    px = sx + t * (tx - sx)
                    py = sy + t * (ty - sy)
                    cx = min(int(px / grid_size), cols - 1)
                    cy = min(int(py / grid_size), rows - 1)
                    density[cy][cx] += net.traffic * 0.05

        max_density = max(max(row) for row in density)
        return min(1.0, max_density / 2.5)

    def _estimate_utilization(self, layout: Layout) -> float:
        chip_area = layout.chip.width * layout.chip.height
        if chip_area <= 0:
            return 0.0
        block_area = sum(b.width * b.height for b in layout.blocks)
        return min(1.0, block_area / chip_area)

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
