"use client";

import { useEffect } from "react";
import Link from "next/link";
import Header from "@/components/Header";
import { useLayoutStore, formatMetricDelta, metricColor } from "@/store/layoutStore";
import type { Metrics } from "@/lib/types";

export default function ComparePage() {
  const loadExample = useLayoutStore((s) => s.loadExample);
  const currentLayout = useLayoutStore((s) => s.currentLayout);
  const candidates = useLayoutStore((s) => s.candidates);
  const generateCandidates = useLayoutStore((s) => s.generateCandidates);
  const loadCandidate = useLayoutStore((s) => s.loadCandidate);
  const loading = useLayoutStore((s) => s.loading);

  useEffect(() => {
    if (!currentLayout) loadExample();
  }, [currentLayout, loadExample]);

  useEffect(() => {
    if (currentLayout && candidates.length === 0) {
      generateCandidates();
    }
  }, [currentLayout, candidates.length, generateCandidates]);

  const baselineMetrics = currentLayout?.metrics;

  return (
    <div className="h-screen flex flex-col">
      <Header />
      <main className="flex-1 overflow-auto p-6">
        <div className="max-w-6xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-lg font-semibold text-chip-text">
                Candidate Comparison
              </h1>
              <p className="text-sm text-chip-muted mt-1">
                Compare layout alternatives by timing, congestion, and wire length metrics.
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => generateCandidates()}
                disabled={loading}
                className="px-4 py-2 text-sm rounded border border-chip-border text-chip-accent hover:bg-chip-border/50 disabled:opacity-50"
              >
                Regenerate
              </button>
              <Link
                href="/"
                className="px-4 py-2 text-sm rounded bg-chip-accent text-chip-bg font-semibold hover:opacity-90"
              >
                Back to Editor
              </Link>
            </div>
          </div>

          {loading && candidates.length === 0 ? (
            <div className="text-center text-chip-muted py-20">Generating candidates...</div>
          ) : (
            <>
              {/* Comparison table */}
              <div className="panel overflow-x-auto mb-6">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-chip-border text-chip-muted text-xs uppercase">
                      <th className="text-left p-3">Metric</th>
                      <th className="text-right p-3">Baseline</th>
                      {candidates.map((c) => (
                        <th key={c.id} className="text-right p-3 font-mono text-chip-accent">
                          {c.name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {baselineMetrics &&
                      METRIC_ROWS.map(({ key, label, unit, invert }) => (
                        <tr key={key} className="border-b border-chip-border/50">
                          <td className="p-3 text-chip-text">{label}</td>
                          <td className="p-3 text-right font-mono">
                            {formatMetric(baselineMetrics, key, unit)}
                          </td>
                          {candidates.map((c) => {
                            const val = c.layout.metrics?.[key as keyof Metrics];
                            const delta = c.metric_deltas[key] ?? 0;
                            return (
                              <td key={c.id} className="p-3 text-right font-mono">
                                <div>{formatMetric(c.layout.metrics!, key, unit)}</div>
                                <div className={`text-[10px] ${metricColor(delta, invert)}`}>
                                  {formatMetricDelta(delta)}
                                </div>
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>

              {/* Candidate cards */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {candidates.map((c) => (
                  <div key={c.id} className="panel p-4 flex flex-col">
                    <div className="mb-2 flex items-center justify-between">
                      <h3 className="font-mono text-chip-accent">{c.name}</h3>
                      {c.objective && (
                        <span className="rounded-full border border-chip-accent2/30 bg-chip-accent2/10 px-2 py-0.5 text-[9px] uppercase text-chip-accent2">
                          {c.objective}
                        </span>
                      )}
                    </div>
                    <p className="mb-3 flex-1 text-xs leading-relaxed text-chip-text">{c.explanation}</p>
                    {c.tradeoff && (
                      <p className="mb-3 rounded border border-chip-border bg-chip-bg px-2 py-1.5 text-[10px] leading-snug text-chip-warn">
                        ⚖ {c.tradeoff}
                      </p>
                    )}
                    {c.layout.metrics && (
                      <div className="mb-4 grid grid-cols-2 gap-2 font-mono text-[10px]">
                        <MiniMetric label="WNS" value={`${c.layout.metrics.wns} ns`} />
                        <MiniMetric label="Congestion" value={c.layout.metrics.congestion_score.toFixed(2)} />
                        <MiniMetric label="Wire Len" value={`${c.layout.metrics.wire_length.toFixed(0)} μm`} />
                        <MiniMetric label="DRC" value={String(c.layout.metrics.drc_count)} />
                      </div>
                    )}
                    <button
                      onClick={() => loadCandidate(c.id)}
                      className="w-full rounded border border-chip-accent/30 bg-chip-accent/20 py-2 text-xs text-chip-accent hover:bg-chip-accent/30"
                    >
                      Load onto canvas
                    </button>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}

const METRIC_ROWS = [
  { key: "wns", label: "WNS (ns)", unit: "", invert: false },
  { key: "tns", label: "TNS (ns)", unit: "", invert: false },
  { key: "violating_paths", label: "Violating Paths", unit: "", invert: true },
  { key: "wire_length", label: "Wire Length (μm)", unit: "", invert: true },
  { key: "congestion_score", label: "Congestion Score", unit: "", invert: true },
  { key: "area_utilization", label: "Area Utilization", unit: "%", invert: false },
  { key: "power_estimate", label: "Power Estimate (W)", unit: "", invert: true },
  { key: "drc_count", label: "DRC Violations", unit: "", invert: true },
];

function formatMetric(metrics: Metrics, key: string, unit: string): string {
  const val = metrics[key as keyof Metrics];
  if (key === "area_utilization") return `${(val * 100).toFixed(0)}%`;
  if (typeof val === "number") return unit ? `${val.toFixed(2)}${unit}` : String(val);
  return String(val);
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-chip-bg rounded px-2 py-1 border border-chip-border">
      <span className="text-chip-muted">{label}: </span>
      <span className="text-chip-text">{value}</span>
    </div>
  );
}
