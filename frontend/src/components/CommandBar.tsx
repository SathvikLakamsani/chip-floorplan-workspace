"use client";

import { useState } from "react";
import { useLayoutStore, formatMetricDelta, metricColor } from "@/store/layoutStore";

const RULE_COMMANDS = [
  "Move SRAM closer to compute",
  "Lock the PLL",
  "Optimize for timing",
  "Reduce congestion near the top right",
  "Generate three candidate layouts",
];

const AI_COMMANDS = [
  "Push the SRAM banks toward the bottom-left corner",
  "Give the NoC router more breathing room",
  "Cluster everything on the critical datapath together",
];

export default function CommandBar() {
  const [command, setCommand] = useState("");
  const submitCommand = useLayoutStore((s) => s.submitCommand);
  const pendingCommand = useLayoutStore((s) => s.pendingCommand);
  const applyPendingCommand = useLayoutStore((s) => s.applyPendingCommand);
  const cancelPendingCommand = useLayoutStore((s) => s.cancelPendingCommand);
  const loading = useLayoutStore((s) => s.loading);
  const error = useLayoutStore((s) => s.error);
  const undo = useLayoutStore((s) => s.undo);
  const exportCurrent = useLayoutStore((s) => s.exportCurrent);
  const historyIndex = useLayoutStore((s) => s.historyIndex);
  const config = useLayoutStore((s) => s.config);

  const llmEnabled = config?.llm_enabled ?? false;
  const exampleCommands = llmEnabled
    ? [...RULE_COMMANDS.slice(0, 3), ...AI_COMMANDS]
    : RULE_COMMANDS;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!command.trim()) return;
    await submitCommand(command.trim());
    setCommand("");
  };

  return (
    <div className="border-t border-chip-border bg-chip-panel shrink-0">
      {/* Command preview modal */}
      {pendingCommand && (
        <div className="px-4 py-3 border-b border-chip-border bg-chip-bg/80">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <h4 className="text-xs font-semibold text-chip-accent uppercase mb-1 flex items-center gap-2">
                Proposed Actions
                {pendingCommand.source === "llm" && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-chip-accent2/20 text-chip-accent2 border border-chip-accent2/30 normal-case">
                    via AI
                  </span>
                )}
                {pendingCommand.source === "rule" && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-chip-border text-chip-muted normal-case">
                    via rules
                  </span>
                )}
              </h4>
              <p className="text-xs text-chip-text mb-2">
                {pendingCommand.explanation}
              </p>
              <ul className="space-y-1 mb-2">
                {pendingCommand.actions.map((action, i) => (
                  <li
                    key={i}
                    className="text-xs font-mono px-2 py-1 rounded bg-chip-panel border border-chip-border"
                  >
                    <span className="text-chip-accent2">{action.type}</span>
                    {action.targets.length > 0 && (
                      <span className="text-chip-muted ml-2">
                        → {action.targets.join(", ")}
                      </span>
                    )}
                    <p className="text-chip-muted text-[10px] mt-0.5">
                      {action.reason}
                    </p>
                  </li>
                ))}
              </ul>

              {Object.keys(pendingCommand.expected_metric_delta).length > 0 && (
                <div className="flex flex-wrap gap-3 text-[10px] font-mono">
                  <span className="text-chip-muted">Expected impact:</span>
                  {Object.entries(pendingCommand.expected_metric_delta).map(
                    ([key, delta]) => (
                      <span key={key} className={metricColor(delta, key.includes("congestion") || key.includes("wire"))}>
                        {key}: {formatMetricDelta(delta as number)}
                      </span>
                    )
                  )}
                </div>
              )}
            </div>

            <div className="flex gap-2 shrink-0">
              <button
                onClick={() => applyPendingCommand()}
                disabled={loading}
                className="px-3 py-1.5 text-xs rounded bg-chip-accent text-chip-bg font-semibold hover:opacity-90 disabled:opacity-50"
              >
                Apply
              </button>
              <button
                onClick={() => cancelPendingCommand()}
                className="px-3 py-1.5 text-xs rounded border border-chip-border text-chip-muted hover:text-chip-text"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="px-4 py-2 text-xs text-chip-danger bg-chip-danger/10 border-b border-chip-border">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex items-center gap-2 px-4 py-2">
        <span className="text-chip-accent font-mono text-sm shrink-0">›</span>
        <input
          type="text"
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          placeholder={
            llmEnabled
              ? "Ask in plain English... (e.g. 'push the memory banks toward the bottom-left')"
              : "Enter layout command... (e.g. 'move SRAM closer to compute')"
          }
          className="flex-1 bg-transparent text-sm font-mono text-chip-text placeholder:text-chip-muted focus:outline-none"
          disabled={loading}
        />
        <span
          title={
            llmEnabled
              ? `AI parser active (${config?.llm_provider} · ${config?.llm_model})`
              : "Rule-based parser only. Set an API key to enable open-ended AI commands."
          }
          className={`text-[9px] px-2 py-0.5 rounded-full border shrink-0 ${
            llmEnabled
              ? "bg-chip-accent/15 text-chip-accent border-chip-accent/30"
              : "bg-chip-border/40 text-chip-muted border-chip-border"
          }`}
        >
          {llmEnabled ? "AI ✦" : "rules only"}
        </span>
        <button
          type="submit"
          disabled={loading || !command.trim()}
          className="px-3 py-1 text-xs rounded bg-chip-accent2/20 text-chip-accent2 border border-chip-accent2/30 hover:bg-chip-accent2/30 disabled:opacity-50"
        >
          Parse
        </button>
        <button
          type="button"
          onClick={() => undo()}
          disabled={historyIndex <= 0}
          className="px-3 py-1 text-xs rounded border border-chip-border text-chip-muted hover:text-chip-text disabled:opacity-30"
        >
          Undo
        </button>
        <button
          type="button"
          onClick={() => exportCurrent("json")}
          className="px-3 py-1 text-xs rounded border border-chip-border text-chip-muted hover:text-chip-text"
        >
          Export JSON
        </button>
      </form>

      <div className="px-4 pb-2 flex flex-wrap gap-1">
        {exampleCommands.map((cmd) => (
          <button
            key={cmd}
            type="button"
            onClick={() => setCommand(cmd)}
            className="text-[10px] px-2 py-0.5 rounded-full border border-chip-border text-chip-muted hover:text-chip-accent hover:border-chip-accent/30"
          >
            {cmd}
          </button>
        ))}
      </div>
    </div>
  );
}
