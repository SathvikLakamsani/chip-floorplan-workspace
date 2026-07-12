"use client";

import { useLayoutStore } from "@/store/layoutStore";
import { blockClass, blockType, getBlockStyle } from "@/lib/blockStyles";

const ORIENTATIONS = ["N", "S", "E", "W", "FN", "FS", "FE", "FW"];

export default function Inspector() {
  const currentLayout = useLayoutStore((s) => s.currentLayout);
  const selectedBlockId = useLayoutStore((s) => s.selectedBlockId);
  const updateBlock = useLayoutStore((s) => s.updateBlock);
  const analyze = useLayoutStore((s) => s.analyze);
  const pushHistory = useLayoutStore((s) => s.pushHistory);

  if (!currentLayout) return null;
  const block = currentLayout.blocks.find((b) => b.id === selectedBlockId);

  if (!block) {
    return (
      <div className="p-4 text-xs text-chip-muted">
        Select a block on the canvas to inspect and edit its physical-design
        properties.
      </div>
    );
  }

  const style = getBlockStyle(block);
  const connectedNets = currentLayout.nets.filter(
    (n) => n.source === block.id || n.sinks.includes(block.id)
  );
  const area = block.width * block.height;
  const powerDensity = area > 0 ? block.power / area : 0;

  const commit = () => {
    pushHistory("Edited block");
    void analyze();
  };

  return (
    <div className="flex flex-col gap-4 overflow-y-auto scrollbar-thin p-3">
      <div className="flex items-center gap-2">
        <span className="h-3.5 w-3.5 rounded" style={{ backgroundColor: style.stroke }} />
        <h3 className="font-mono text-sm text-chip-accent">{block.name}</h3>
      </div>

      <FieldGrid>
        <Field label="ID" value={block.id} mono />
        <Field label="Type" value={blockType(block)} />
        <Field label="Class" value={blockClass(block)} />
        <Field
          label="Placement"
          value={String(block.placement_status)}
        />
      </FieldGrid>

      {/* Geometry */}
      <Section label="Geometry">
        <FieldGrid>
          <NumberField label="X (µm)" value={block.x} disabled={block.fixed} onChange={(v) => updateBlock(block.id, { x: v })} onBlur={commit} />
          <NumberField label="Y (µm)" value={block.y} disabled={block.fixed} onChange={(v) => updateBlock(block.id, { y: v })} onBlur={commit} />
          <NumberField label="Width" value={block.width} disabled={block.fixed} onChange={(v) => updateBlock(block.id, { width: v })} onBlur={commit} />
          <NumberField label="Height" value={block.height} disabled={block.fixed} onChange={(v) => updateBlock(block.id, { height: v })} onBlur={commit} />
        </FieldGrid>
        <FieldGrid className="mt-2">
          <Field label="Area" value={`${area.toFixed(0)} µm²`} />
          <div>
            <label className="text-[10px] text-chip-muted">Orientation</label>
            <select
              value={String(block.orientation)}
              onChange={(e) => {
                updateBlock(block.id, { orientation: e.target.value });
                commit();
              }}
              className="mt-0.5 w-full rounded border border-chip-border bg-chip-bg px-2 py-1 font-mono text-xs text-chip-text focus:border-chip-accent focus:outline-none"
            >
              {ORIENTATIONS.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </div>
        </FieldGrid>
      </Section>

      {/* Movable / keepout toggles */}
      <div className="flex flex-wrap gap-2">
        <Toggle
          label={block.fixed ? "Fixed" : "Movable"}
          on={block.fixed}
          onClick={() => {
            updateBlock(block.id, {
              fixed: !block.fixed,
              placement_status: !block.fixed ? "fixed" : "placed",
            });
            commit();
          }}
        />
        <Toggle
          label="Keepout"
          on={block.keepout}
          onClick={() => {
            const on = !block.keepout;
            updateBlock(block.id, {
              keepout: on,
              halo: on ? { left: 20, right: 20, top: 20, bottom: 20 } : null,
            });
            commit();
          }}
        />
      </div>

      {/* Electrical */}
      <Section label="Electrical / Timing">
        <FieldGrid>
          <NumberField label="Power (W)" value={block.power} step={0.1} onChange={(v) => updateBlock(block.id, { power: v })} onBlur={commit} />
          <Field label="Power Density" value={`${powerDensity.toFixed(4)} W/µm²`} />
          <NumberField label="Criticality" value={block.criticality} step={0.05} min={0} max={1} onChange={(v) => updateBlock(block.id, { criticality: v })} onBlur={commit} />
          <Field label="Clock" value={block.clock_domain || "—"} />
          <Field label="Voltage" value={block.voltage_domain || "—"} />
          {block.instance_count ? <Field label="Instances" value={String(block.instance_count)} /> : null}
        </FieldGrid>
      </Section>

      {/* Pins */}
      {block.pins.length > 0 && (
        <Section label={`Pins (${block.pins.length})`}>
          <ul className="space-y-1">
            {block.pins.map((p, i) => (
              <li key={i} className="flex items-center justify-between rounded border border-chip-border bg-chip-bg px-2 py-1 font-mono text-[10px]">
                <span className="text-chip-text">{p.name}</span>
                <span className="text-chip-muted">
                  {String(p.type)} · {String(p.side)}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Connected nets */}
      {connectedNets.length > 0 && (
        <Section label={`Connected Nets (${connectedNets.length})`}>
          <ul className="space-y-1">
            {connectedNets.map((net) => (
              <li key={net.id} className="rounded border border-chip-border bg-chip-bg px-2 py-1 font-mono text-[10px]">
                <span className="text-chip-accent">{net.name || net.id}</span>
                <span className="ml-2 text-chip-muted">
                  crit {net.criticality.toFixed(2)} · {String(net.type)}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-chip-muted">
        {label}
      </h4>
      {children}
    </div>
  );
}

function FieldGrid({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`grid grid-cols-2 gap-2 ${className}`}>{children}</div>;
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <label className="text-[10px] text-chip-muted">{label}</label>
      <div className={`mt-0.5 truncate text-xs ${mono ? "font-mono" : ""} text-chip-text`}>{value}</div>
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  onBlur,
  disabled,
  step = 1,
  min,
  max,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  onBlur?: () => void;
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
        value={Number.isFinite(value) ? Math.round(value * 100) / 100 : 0}
        step={step}
        min={min}
        max={max}
        disabled={disabled}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        onBlur={onBlur}
        className="mt-0.5 w-full rounded border border-chip-border bg-chip-bg px-2 py-1 font-mono text-xs text-chip-text focus:border-chip-accent focus:outline-none disabled:opacity-50"
      />
    </div>
  );
}

function Toggle({ label, on, onClick }: { label: string; on: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 rounded-md border px-2.5 py-1 font-mono text-[11px] ${
        on ? "border-chip-accent/60 bg-chip-accent/10 text-chip-accent" : "border-chip-border text-chip-muted hover:text-chip-text"
      }`}
    >
      <span className={`h-2 w-2 rounded-full ${on ? "bg-chip-accent" : "bg-chip-border"}`} />
      {label}
    </button>
  );
}
