"use client";

import { useState } from "react";
import { useLayoutStore, formatMetricDelta, metricColor } from "@/store/layoutStore";

const RULE_COMMANDS = [
  "make sure nothing overlaps",
  "move SRAM closer to compute",
  "lock the PLL",
  "add keepout around PLL",
  "show congestion",
  "show timing paths",
  "optimize for timing",
  "explain why WNS is negative",
  "generate three candidate layouts",
];

const AI_COMMANDS = [
  "add a new SRAM bank near the compute array",
  "add an accelerator block and connect it to the NoC",
  "duplicate SRAM Bank 0",
  "delete the control unit",
  "make the die 20% bigger",
  "give the NoC router more breathing room",
];

export default function CommandBar() {
  const [command, setCommand] = useState("");
  const submitCommand = useLayoutStore((s) => s.submitCommand);
  const pendingCommand = useLayoutStore((s) => s.pendingCommand);
  const applyPendingCommand = useLayoutStore((s) => s.applyPendingCommand);
  const cancelPendingCommand = useLayoutStore((s) => s.cancelPendingCommand);
  const loading = useLayoutStore((s) => s.loading);
  const error = useLayoutStore((s) => s.error);
  const notice = useLayoutStore((s) => s.notice);
  const clearNotice = useLayoutStore((s) => s.clearNotice);
  const undo = useLayoutStore((s) => s.undo);
  const exportCurrent = useLayoutStore((s) => s.exportCurrent);
  const historyIndex = useLayoutStore((s) => s.historyIndex);
  const config = useLayoutStore((s) => s.config);

  const llmEnabled = config?.llm_enabled ?? false;
  const exampleCommands = llmEnabled ? [...RULE_COMMANDS.slice(0, 5), ...AI_COMMANDS] : RULE_COMMANDS;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!command.trim()) return;
    await submitCommand(command.trim());
    setCommand("");
  };

  return (
    <div className="shrink-0 border-t border-chip-border bg-chip-panel">
      {/* Command preview */}
      {pendingCommand && (
        <div className="border-b border-chip-border bg-chip-bg/80 px-4 py-3">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <h4 className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase text-chip-accent">
                Proposed Actions — Preview
                {pendingCommand.source === "llm" && (
                  <span className="rounded-full border border-chip-accent2/30 bg-chip-accent2/20 px-1.5 py-0.5 text-[9px] normal-case text-chip-accent2">via AI</span>
                )}
                {pendingCommand.source === "rule" && (
                  <span className="rounded-full bg-chip-border px-1.5 py-0.5 text-[9px] normal-case text-chip-muted">via rules</span>
                )}
              </h4>
              <p className="mb-2 text-xs text-chip-text">{pendingCommand.explanation}</p>
              <ul className="mb-2 space-y-1">
                {pendingCommand.actions.map((action, i) => (
                  <li key={i} className="rounded border border-chip-border bg-chip-panel px-2 py-1 font-mono text-xs">
                    <span className="text-chip-accent2">{action.type}</span>
                    {action.targets.length > 0 && <span className="ml-2 text-chip-muted">→ {action.targets.join(", ")}</span>}
                    <p className="mt-0.5 text-[10px] text-chip-muted">{action.reason}</p>
                  </li>
                ))}
              </ul>
              {Object.keys(pendingCommand.expected_metric_delta).length > 0 && (
                <div className="flex flex-wrap gap-3 font-mono text-[10px]">
                  <span className="text-chip-muted">Expected impact:</span>
                  {Object.entries(pendingCommand.expected_metric_delta).map(([key, delta]) => (
                    <span key={key} className={metricColor(delta as number, key.includes("congestion") || key.includes("wire") || key.includes("drc"))}>
                      {key}: {formatMetricDelta(delta as number, key === "drc_count" ? 0 : 3)}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="flex shrink-0 gap-2">
              <button onClick={() => applyPendingCommand()} disabled={loading} className="rounded bg-chip-accent px-3 py-1.5 text-xs font-semibold text-chip-bg hover:opacity-90 disabled:opacity-50">
                Apply
              </button>
              <button onClick={() => cancelPendingCommand()} className="rounded border border-chip-border px-3 py-1.5 text-xs text-chip-muted hover:text-chip-text">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {notice && !pendingCommand && (
        <div className="flex items-center justify-between border-b border-chip-border bg-chip-accent/5 px-4 py-2 text-xs text-chip-accent">
          <span>{notice}</span>
          <button onClick={clearNotice} className="text-chip-muted hover:text-chip-text">✕</button>
        </div>
      )}

      {error && (
        <div className="border-b border-chip-border bg-chip-danger/10 px-4 py-2 text-xs text-chip-danger">{error}</div>
      )}

      <form onSubmit={handleSubmit} className="flex items-center gap-2 px-4 py-2">
        <span className="shrink-0 font-mono text-sm text-chip-accent">›</span>
        <input
          type="text"
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          placeholder={llmEnabled ? "Ask in plain English… (e.g. 'give the NoC more breathing room')" : "Enter a command… (e.g. 'make sure nothing overlaps')"}
          className="flex-1 bg-transparent font-mono text-sm text-chip-text placeholder:text-chip-muted focus:outline-none"
          disabled={loading}
        />
        <span
          title={llmEnabled ? `AI parser active (${config?.llm_provider} · ${config?.llm_model})` : "Rule-based parser only. Set an API key to enable open-ended AI commands."}
          className={`shrink-0 rounded-full border px-2 py-0.5 text-[9px] ${llmEnabled ? "border-chip-accent/30 bg-chip-accent/15 text-chip-accent" : "border-chip-border bg-chip-border/40 text-chip-muted"}`}
        >
          {llmEnabled ? "AI ✦" : "rules only"}
        </span>
        <button type="submit" disabled={loading || !command.trim()} className="rounded border border-chip-accent2/30 bg-chip-accent2/20 px-3 py-1 text-xs text-chip-accent2 hover:bg-chip-accent2/30 disabled:opacity-50">
          Run
        </button>
        <button type="button" onClick={() => undo()} disabled={historyIndex <= 0} className="rounded border border-chip-border px-3 py-1 text-xs text-chip-muted hover:text-chip-text disabled:opacity-30">
          Undo
        </button>
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-chip-muted">Export:</span>
          {(["json", "def", "tcl"] as const).map((f) => (
            <button key={f} type="button" onClick={() => exportCurrent(f)} className="rounded border border-chip-border px-2 py-1 text-[10px] uppercase text-chip-muted hover:border-chip-accent/30 hover:text-chip-accent">
              {f}
            </button>
          ))}
        </div>
      </form>

      <div className="flex flex-wrap gap-1 px-4 pb-2">
        {exampleCommands.map((cmd) => (
          <button
            key={cmd}
            type="button"
            onClick={() => setCommand(cmd)}
            className="rounded-full border border-chip-border px-2 py-0.5 text-[10px] text-chip-muted hover:border-chip-accent/30 hover:text-chip-accent"
          >
            {cmd}
          </button>
        ))}
      </div>
    </div>
  );
}
