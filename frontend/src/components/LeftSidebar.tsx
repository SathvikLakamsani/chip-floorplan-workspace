"use client";

import { getBlockColors } from "./BlockNode";
import { useLayoutStore } from "@/store/layoutStore";

export default function LeftSidebar() {
  const currentLayout = useLayoutStore((s) => s.currentLayout);
  const selectedBlockId = useLayoutStore((s) => s.selectedBlockId);
  const setSelectedBlock = useLayoutStore((s) => s.setSelectedBlock);
  const candidates = useLayoutStore((s) => s.candidates);
  const loadCandidate = useLayoutStore((s) => s.loadCandidate);
  const generateCandidates = useLayoutStore((s) => s.generateCandidates);
  const loading = useLayoutStore((s) => s.loading);

  if (!currentLayout) return null;

  return (
    <aside className="w-64 shrink-0 panel flex flex-col overflow-hidden">
      <Section title="Blocks" count={currentLayout.blocks.length} className="max-h-[38%]">
        <ul className="space-y-1">
          {currentLayout.blocks.map((block) => {
            const colors = getBlockColors(block.type);
            return (
              <li key={block.id}>
                <button
                  onClick={() => setSelectedBlock(block.id)}
                  className={`w-full text-left px-2 py-1.5 rounded text-xs flex items-center gap-2 transition-colors ${
                    selectedBlockId === block.id
                      ? "bg-chip-border"
                      : "hover:bg-chip-border/50"
                  }`}
                >
                  <span
                    className="w-2 h-2 rounded-sm shrink-0"
                    style={{ backgroundColor: colors.border }}
                  />
                  <span className="font-mono truncate">{block.name}</span>
                  {block.fixed && (
                    <span className="ml-auto text-chip-warn text-[10px]">🔒</span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </Section>

      <Section title="Constraints" count={currentLayout.constraints.length} className="max-h-[32%]">
        <ul className="space-y-2">
          {currentLayout.constraints.map((c) => (
            <li
              key={c.id}
              className="text-xs px-2 py-1.5 rounded bg-chip-bg border border-chip-border"
            >
              <div className="flex items-center gap-1 mb-0.5">
                <span className="text-chip-accent2 font-mono text-[10px] uppercase">
                  {c.type}
                </span>
                <span
                  className={`ml-auto text-[10px] px-1 rounded ${
                    c.priority === "high"
                      ? "text-chip-danger"
                      : c.priority === "medium"
                      ? "text-chip-warn"
                      : "text-chip-muted"
                  }`}
                >
                  {c.priority}
                </span>
              </div>
              <p className="text-chip-muted leading-snug">{c.description}</p>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Candidates" count={candidates.length} className="flex-1">
        {candidates.length === 0 ? (
          <button
            onClick={() => generateCandidates()}
            disabled={loading}
            className="w-full text-xs px-2 py-2 rounded border border-chip-border text-chip-accent hover:bg-chip-border/50 disabled:opacity-50"
          >
            Generate 3 candidates
          </button>
        ) : (
          <ul className="space-y-1">
            {candidates.map((c) => (
              <li key={c.id}>
                <button
                  onClick={() => loadCandidate(c.id)}
                  className="w-full text-left px-2 py-1.5 rounded text-xs hover:bg-chip-border/50"
                >
                  <span className="font-mono text-chip-accent">{c.name}</span>
                  <p className="text-chip-muted text-[10px] mt-0.5 line-clamp-2">
                    {c.explanation}
                  </p>
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
    <div className={`border-b border-chip-border flex flex-col min-h-0 overflow-hidden ${className}`}>
      <div className="px-3 py-2 flex items-center gap-2 shrink-0">
        <h3 className="text-xs font-semibold text-chip-text uppercase tracking-wider">
          {title}
        </h3>
        <span className="text-[10px] text-chip-muted font-mono">{count}</span>
      </div>
      <div className="px-2 pb-3 overflow-y-auto scrollbar-thin flex-1">
        {children}
      </div>
    </div>
  );
}
