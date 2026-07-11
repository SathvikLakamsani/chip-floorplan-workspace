"use client";

import { useLayoutStore } from "@/store/layoutStore";
import { getBlockColors } from "./BlockNode";

export default function RightInspector() {
  const currentLayout = useLayoutStore((s) => s.currentLayout);
  const selectedBlockId = useLayoutStore((s) => s.selectedBlockId);
  const updateBlock = useLayoutStore((s) => s.updateBlock);
  const analyze = useLayoutStore((s) => s.analyze);
  const explanations = useLayoutStore((s) => s.explanations);
  const loading = useLayoutStore((s) => s.loading);

  if (!currentLayout) return null;

  const block = currentLayout.blocks.find((b) => b.id === selectedBlockId);
  const connectedNets = currentLayout.nets.filter(
    (n) =>
      n.source === selectedBlockId ||
      n.sinks.includes(selectedBlockId || "")
  );

  return (
    <aside className="w-72 shrink-0 panel flex flex-col overflow-hidden">
      {/* Metrics summary */}
      {currentLayout.metrics && (
        <div className="p-3 border-b border-chip-border">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-chip-muted mb-2">
            Metrics
          </h3>
          <div className="grid grid-cols-2 gap-2">
            <Metric label="WNS" value={`${currentLayout.metrics.wns} ns`} good={currentLayout.metrics.wns >= 0} />
            <Metric label="TNS" value={`${currentLayout.metrics.tns} ns`} good={currentLayout.metrics.tns >= 0} />
            <Metric label="Wire Len" value={`${currentLayout.metrics.wire_length.toFixed(0)} μm`} />
            <Metric label="Congestion" value={currentLayout.metrics.congestion_score.toFixed(2)} good={currentLayout.metrics.congestion_score < 0.6} />
            <Metric label="Utilization" value={`${(currentLayout.metrics.area_utilization * 100).toFixed(0)}%`} />
            <Metric label="Power" value={`${currentLayout.metrics.power_estimate} W`} />
          </div>
          <button
            onClick={() => analyze()}
            disabled={loading}
            className="mt-2 w-full text-xs py-1.5 rounded border border-chip-border text-chip-accent2 hover:bg-chip-border/50 disabled:opacity-50"
          >
            Re-analyze
          </button>
        </div>
      )}

      {/* Block inspector */}
      {block ? (
        <div className="p-3 border-b border-chip-border overflow-y-auto scrollbar-thin flex-1">
          <div className="flex items-center gap-2 mb-3">
            <span
              className="w-3 h-3 rounded"
              style={{ backgroundColor: getBlockColors(block.type).border }}
            />
            <h3 className="font-mono text-sm text-chip-accent">{block.name}</h3>
          </div>

          <FieldGrid>
            <Field label="ID" value={block.id} mono />
            <Field label="Type" value={block.type} />
            <NumberField label="X" value={block.x} onChange={(v) => updateBlock(block.id, { x: v })} disabled={block.fixed} />
            <NumberField label="Y" value={block.y} onChange={(v) => updateBlock(block.id, { y: v })} disabled={block.fixed} />
            <NumberField label="Width" value={block.width} onChange={(v) => updateBlock(block.id, { width: v })} disabled={block.fixed} />
            <NumberField label="Height" value={block.height} onChange={(v) => updateBlock(block.id, { height: v })} disabled={block.fixed} />
          </FieldGrid>

          <div className="mt-3 flex items-center gap-2">
            <label className="text-xs text-chip-muted">Fixed</label>
            <button
              onClick={() => updateBlock(block.id, { fixed: !block.fixed })}
              className={`w-10 h-5 rounded-full transition-colors ${
                block.fixed ? "bg-chip-accent" : "bg-chip-border"
              }`}
            >
              <div
                className={`w-4 h-4 rounded-full bg-white transition-transform mx-0.5 ${
                  block.fixed ? "translate-x-5" : ""
                }`}
              />
            </button>
          </div>

          <FieldGrid className="mt-3">
            <NumberField label="Power (W)" value={block.power} step={0.1} onChange={(v) => updateBlock(block.id, { power: v })} />
            <Field label="Clock" value={block.clock_domain} />
            <Field label="Voltage" value={block.voltage_domain} />
            <NumberField label="Criticality" value={block.criticality} step={0.05} min={0} max={1} onChange={(v) => updateBlock(block.id, { criticality: v })} />
          </FieldGrid>

          {connectedNets.length > 0 && (
            <div className="mt-4">
              <h4 className="text-xs text-chip-muted uppercase mb-2">Connected Nets</h4>
              <ul className="space-y-1">
                {connectedNets.map((net) => (
                  <li
                    key={net.id}
                    className="text-[10px] font-mono px-2 py-1 rounded bg-chip-bg border border-chip-border"
                  >
                    <span className="text-chip-accent">{net.id}</span>
                    <span className="text-chip-muted ml-2">
                      crit={net.criticality.toFixed(2)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <div className="p-3 text-xs text-chip-muted flex-1">
          Select a block to inspect properties
        </div>
      )}

      {/* Analysis explanations */}
      {explanations.length > 0 && (
        <div className="p-3 border-t border-chip-border max-h-40 overflow-y-auto scrollbar-thin">
          <h4 className="text-xs text-chip-muted uppercase mb-2">Analysis</h4>
          <ul className="space-y-1">
            {explanations.map((exp, i) => (
              <li key={i} className="text-[11px] text-chip-text leading-snug">
                • {exp}
              </li>
            ))}
          </ul>
        </div>
      )}
    </aside>
  );
}

function Metric({
  label,
  value,
  good,
}: {
  label: string;
  value: string;
  good?: boolean;
}) {
  return (
    <div className="bg-chip-bg rounded px-2 py-1.5 border border-chip-border">
      <div className="text-[10px] text-chip-muted">{label}</div>
      <div
        className={`text-xs font-mono ${
          good === undefined
            ? "text-chip-text"
            : good
            ? "text-chip-accent"
            : "text-chip-danger"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function FieldGrid({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`grid grid-cols-2 gap-2 ${className}`}>{children}</div>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <label className="text-[10px] text-chip-muted">{label}</label>
      <div
        className={`text-xs mt-0.5 ${mono ? "font-mono" : ""} text-chip-text truncate`}
      >
        {value}
      </div>
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  disabled,
  step = 1,
  min,
  max,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  disabled?: boolean;
  step?: number;
  min?: number;
  max?: number;
}) {
  return (
    <div>
      <label className="text-[10px] text-chip-muted">{label}</label>
      <input
        type="number"
        value={value}
        step={step}
        min={min}
        max={max}
        disabled={disabled}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        className="w-full mt-0.5 text-xs font-mono bg-chip-bg border border-chip-border rounded px-2 py-1 text-chip-text disabled:opacity-50 focus:outline-none focus:border-chip-accent"
      />
    </div>
  );
}
