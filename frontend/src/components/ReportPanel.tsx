"use client";

import { useMemo } from "react";
import { useLayoutStore } from "@/store/layoutStore";
import type { Block, Layout } from "@/lib/types";

function center(b: Block) {
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
}

function netLength(layout: Layout, source: string, sink: string): number {
  const bm: Record<string, Block> = {};
  layout.blocks.forEach((b) => (bm[b.id] = b));
  const s = bm[source];
  const d = bm[sink];
  if (!s || !d) return 0;
  const a = center(s);
  const b = center(d);
  return Math.hypot(a.x - b.x, a.y - b.y);
}

export default function ReportPanel() {
  const layout = useLayoutStore((s) => s.currentLayout);
  const drc = useLayoutStore((s) => s.drc);
  const setSelectedBlock = useLayoutStore((s) => s.setSelectedBlock);
  const analyze = useLayoutStore((s) => s.analyze);
  const loading = useLayoutStore((s) => s.loading);

  const criticalNets = useMemo(() => {
    if (!layout) return [];
    return [...layout.nets]
      .sort((a, b) => b.criticality - a.criticality)
      .slice(0, 6)
      .map((n) => ({
        net: n,
        length: n.sinks.length ? netLength(layout, n.source, n.sinks[0]) : 0,
      }));
  }, [layout]);

  const suggestions = useMemo(() => {
    if (!layout?.metrics) return [];
    const out: string[] = [];
    const m = layout.metrics;
    if (m.wns < 0) out.push("Move timing-critical blocks closer to recover WNS ('optimize for timing').");
    if (m.congestion_score > 0.7) out.push("Spread the densest region to reduce congestion ('optimize for congestion').");
    if (m.area_utilization > 0.8) out.push("Enlarge the core — utilization is high.");
    drc.violations
      .filter((v) => (typeof v.severity === "string" ? v.severity : "") === "error")
      .slice(0, 3)
      .forEach((v) => out.push(v.suggestion));
    if (out.length === 0) out.push("Layout looks healthy — generate candidates to explore trade-offs.");
    return out;
  }, [layout, drc]);

  if (!layout || !layout.metrics) return null;
  const m = layout.metrics;

  return (
    <div className="flex flex-col gap-4 overflow-y-auto scrollbar-thin p-3">
      {/* QoR Summary */}
      <ReportSection title="QoR Summary" action={
        <button onClick={() => analyze()} disabled={loading} className="text-[10px] text-chip-accent2 hover:underline disabled:opacity-50">
          Re-analyze
        </button>
      }>
        <div className="grid grid-cols-2 gap-1.5">
          <Stat label="WNS" value={`${m.wns} ns`} good={m.wns >= 0} />
          <Stat label="TNS" value={`${m.tns} ns`} good={m.tns >= 0} />
          <Stat label="Violating" value={String(m.violating_paths)} good={m.violating_paths === 0} />
          <Stat label="Wire Len" value={`${(m.wire_length / 1000).toFixed(1)}k µm`} />
          <Stat label="Congestion" value={m.congestion_score.toFixed(2)} good={m.congestion_score < 0.6} />
          <Stat label="Utilization" value={`${(m.area_utilization * 100).toFixed(0)}%`} good={m.area_utilization < 0.8} />
          <Stat label="Power" value={`${m.power_estimate} W`} />
          <Stat label="DRC" value={String(m.drc_count)} good={m.drc_count === 0} />
        </div>
      </ReportSection>

      {/* Timing */}
      <ReportSection title={`Timing (${layout.timing_paths.length} paths)`}>
        <ul className="space-y-1.5">
          {layout.timing_paths.slice(0, 5).map((p) => (
            <li key={p.id} className="rounded border border-chip-border bg-chip-bg px-2 py-1.5">
              <div className="flex items-center justify-between font-mono text-[10px]">
                <span className="text-chip-text">
                  {p.startpoint} → {p.endpoint}
                </span>
                <span className={p.slack < 0 ? "text-chip-danger" : "text-chip-accent"}>
                  {p.slack.toFixed(3)} ns
                </span>
              </div>
              <div className="mt-0.5 flex items-center gap-2 text-[9px] text-chip-muted">
                <span>{p.distance.toFixed(0)} µm</span>
                {p.clock && <span>· {p.clock}</span>}
              </div>
              {p.explanation && <p className="mt-1 text-[10px] leading-snug text-chip-muted">{p.explanation}</p>}
            </li>
          ))}
          {layout.timing_paths.length === 0 && <Empty>No timing paths.</Empty>}
        </ul>
      </ReportSection>

      {/* Congestion */}
      <ReportSection title="Congestion">
        {layout.congestion_regions.length === 0 ? (
          <Empty>No congestion hotspots.</Empty>
        ) : (
          <ul className="space-y-1">
            {layout.congestion_regions.slice(0, 4).map((r, i) => (
              <li key={i} className="rounded border border-chip-border bg-chip-bg px-2 py-1 text-[10px]">
                <div className="flex justify-between font-mono">
                  <span className="text-chip-muted">({r.x.toFixed(0)}, {r.y.toFixed(0)})</span>
                  <span className="text-chip-warn">{r.score.toFixed(2)}</span>
                </div>
                <p className="mt-0.5 leading-snug text-chip-muted">{r.reason}</p>
              </li>
            ))}
          </ul>
        )}
      </ReportSection>

      {/* Power */}
      <ReportSection title="Power Density">
        {layout.power_regions.length === 0 ? (
          <Empty>No hotspots.</Empty>
        ) : (
          <ul className="space-y-1">
            {layout.power_regions.slice(0, 4).map((r, i) => (
              <li key={i} className="rounded border border-chip-border bg-chip-bg px-2 py-1 text-[10px]">
                <div className="flex justify-between font-mono">
                  <span className="text-chip-muted">density</span>
                  <span className="text-chip-warn">{r.density.toFixed(2)}</span>
                </div>
                <p className="mt-0.5 leading-snug text-chip-muted">{r.reason}</p>
              </li>
            ))}
          </ul>
        )}
      </ReportSection>

      {/* DRC / Legality */}
      <ReportSection title={`DRC / Legality (${drc.violations.length})`}>
        {drc.violations.length === 0 ? (
          <Empty>No legality violations.</Empty>
        ) : (
          <ul className="space-y-1.5">
            {drc.violations.map((v) => {
              const sev = typeof v.severity === "string" ? v.severity : "warning";
              return (
                <li
                  key={v.id}
                  className={`cursor-pointer rounded px-2 py-1.5 ${sev === "error" ? "sev-error" : sev === "warning" ? "sev-warning" : "sev-info"}`}
                  onClick={() => v.targets[0] && setSelectedBlock(v.targets[0])}
                >
                  <div className="flex items-center gap-1.5">
                    <span className={`font-mono text-[9px] uppercase ${sev === "error" ? "text-chip-danger" : sev === "warning" ? "text-chip-warn" : "text-chip-accent2"}`}>
                      {sev}
                    </span>
                    <span className="font-mono text-[9px] text-chip-muted">{v.rule}</span>
                  </div>
                  <p className="mt-0.5 text-[10px] leading-snug text-chip-text">{v.message}</p>
                  {v.suggestion && <p className="mt-0.5 text-[9px] leading-snug text-chip-muted">↳ {v.suggestion}</p>}
                </li>
              );
            })}
          </ul>
        )}
      </ReportSection>

      {/* Critical Nets */}
      <ReportSection title="Critical Nets">
        <ul className="space-y-1">
          {criticalNets.map(({ net, length }) => (
            <li key={net.id} className="rounded border border-chip-border bg-chip-bg px-2 py-1 text-[10px]">
              <div className="flex justify-between font-mono">
                <span className="text-chip-accent">{net.name || net.id}</span>
                <span className="text-chip-muted">{net.criticality.toFixed(2)}</span>
              </div>
              <div className="mt-0.5 flex justify-between text-[9px] text-chip-muted">
                <span>{net.source} → {net.sinks[0]}</span>
                <span>{length.toFixed(0)} µm</span>
              </div>
            </li>
          ))}
        </ul>
      </ReportSection>

      {/* Suggested Actions */}
      <ReportSection title="Suggested Actions">
        <ul className="space-y-1">
          {suggestions.map((s, i) => (
            <li key={i} className="text-[10px] leading-snug text-chip-text">• {s}</li>
          ))}
        </ul>
      </ReportSection>
    </div>
  );
}

function ReportSection({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <h4 className="text-[10px] font-semibold uppercase tracking-wider text-chip-muted">{title}</h4>
        {action}
      </div>
      {children}
    </div>
  );
}

function Stat({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div className="rounded border border-chip-border bg-chip-bg px-2 py-1">
      <div className="text-[9px] text-chip-muted">{label}</div>
      <div className={`font-mono text-xs ${good === undefined ? "text-chip-text" : good ? "text-chip-accent" : "text-chip-danger"}`}>{value}</div>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-[10px] text-chip-muted">{children}</p>;
}
