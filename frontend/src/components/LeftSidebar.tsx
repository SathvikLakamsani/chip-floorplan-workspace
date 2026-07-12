"use client";

import { useLayoutStore } from "@/store/layoutStore";
import { getBlockStyle, blockClass } from "@/lib/blockStyles";

export default function LeftSidebar() {
  const currentLayout = useLayoutStore((s) => s.currentLayout);
  const selectedBlockId = useLayoutStore((s) => s.selectedBlockId);
  const setSelectedBlock = useLayoutStore((s) => s.setSelectedBlock);
  const candidates = useLayoutStore((s) => s.candidates);
  const loadCandidate = useLayoutStore((s) => s.loadCandidate);
  const generateCandidates = useLayoutStore((s) => s.generateCandidates);
  const loadExample = useLayoutStore((s) => s.loadExample);
  const sourceMode = useLayoutStore((s) => s.sourceMode);
  const loading = useLayoutStore((s) => s.loading);

  if (!currentLayout) return null;

  return (
    <aside className="panel flex w-64 shrink-0 flex-col overflow-hidden">
      {/* Design source */}
      <div className="border-b border-chip-border px-3 py-2">
        <div className="mb-1 flex items-center justify-between">
          <span className="font-mono text-[11px] text-chip-text">{currentLayout.chip.name}</span>
          <span className={`rounded px-1.5 py-0.5 text-[9px] font-mono ${sourceMode === "imported" ? "bg-chip-accent2/20 text-chip-accent2" : "bg-chip-border text-chip-muted"}`}>
            {sourceMode === "imported" ? "IMPORTED" : "DEMO"}
          </span>
        </div>
        {sourceMode === "imported" && (
          <button onClick={() => loadExample()} className="text-[10px] text-chip-accent2 hover:underline">
            ← Back to demo layout
          </button>
        )}
      </div>

      <Section title="Blocks" count={currentLayout.blocks.length} className="max-h-[34%]">
        <ul className="space-y-1">
          {currentLayout.blocks.map((block) => {
            const style = getBlockStyle(block);
            return (
              <li key={block.id}>
                <button
                  onClick={() => setSelectedBlock(block.id)}
                  className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs transition-colors ${
                    selectedBlockId === block.id ? "bg-chip-border" : "hover:bg-chip-border/50"
                  }`}
                >
                  <span className="h-2 w-2 shrink-0 rounded-sm" style={{ backgroundColor: style.stroke }} />
                  <span className="truncate font-mono">{block.name}</span>
                  <span className="ml-auto shrink-0 text-[9px] text-chip-muted">{blockClass(block).replace("_", " ").slice(0, 6)}</span>
                  {block.fixed && <span className="text-[10px] text-chip-warn">🔒</span>}
                </button>
              </li>
            );
          })}
        </ul>
      </Section>

      <Section title="Nets" count={currentLayout.nets.length} className="max-h-[26%]">
        <ul className="space-y-1">
          {[...currentLayout.nets]
            .sort((a, b) => b.criticality - a.criticality)
            .map((n) => (
              <li key={n.id} className="rounded border border-chip-border bg-chip-bg px-2 py-1 text-[10px]">
                <div className="flex items-center justify-between font-mono">
                  <span className="truncate text-chip-text">{n.name || n.id}</span>
                  <span className={n.criticality >= 0.9 ? "text-chip-danger" : "text-chip-muted"}>{n.criticality.toFixed(2)}</span>
                </div>
              </li>
            ))}
        </ul>
      </Section>

      <Section title="Constraints" count={currentLayout.constraints.length} className="max-h-[24%]">
        <ul className="space-y-2">
          {currentLayout.constraints.map((c) => (
            <li key={c.id} className="rounded border border-chip-border bg-chip-bg px-2 py-1.5 text-xs">
              <div className="mb-0.5 flex items-center gap-1">
                <span className="font-mono text-[10px] uppercase text-chip-accent2">{c.type}</span>
                <span className={`ml-auto rounded px-1 text-[10px] ${c.priority === "high" ? "text-chip-danger" : c.priority === "medium" ? "text-chip-warn" : "text-chip-muted"}`}>
                  {c.priority}
                </span>
              </div>
              <p className="leading-snug text-chip-muted">{c.description}</p>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Candidates" count={candidates.length} className="flex-1">
        {candidates.length === 0 ? (
          <button
            onClick={() => generateCandidates()}
            disabled={loading}
            className="w-full rounded border border-chip-border px-2 py-2 text-xs text-chip-accent hover:bg-chip-border/50 disabled:opacity-50"
          >
            Generate 3 candidates
          </button>
        ) : (
          <ul className="space-y-1">
            {candidates.map((c) => (
              <li key={c.id}>
                <button onClick={() => loadCandidate(c.id)} className="w-full rounded px-2 py-1.5 text-left text-xs hover:bg-chip-border/50">
                  <span className="font-mono text-chip-accent">{c.name}</span>
                  <p className="mt-0.5 line-clamp-2 text-[10px] text-chip-muted">{c.explanation}</p>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </aside>
  );
}

function Section({
  title,
  count,
  children,
  className = "",
}: {
  title: string;
  count: number;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex min-h-0 flex-col overflow-hidden border-b border-chip-border ${className}`}>
      <div className="flex shrink-0 items-center gap-2 px-3 py-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-chip-text">{title}</h3>
        <span className="font-mono text-[10px] text-chip-muted">{count}</span>
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin px-2 pb-3">{children}</div>
    </div>
  );
}
