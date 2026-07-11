"use client";

import { useState } from "react";
import { useLayoutStore, formatMetricDelta, metricColor } from "@/store/layoutStore";

const EXAMPLE_COMMANDS = [
  "Move SRAM closer to compute",
  "Lock the PLL",
  "Optimize for timing",
  "Reduce congestion near the top right",
  "Generate three candidate layouts",
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
              <h4 className="text-xs font-semibold text-chip-accent uppercase mb-1">
                Proposed Actions
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
          placeholder="Enter layout command... (e.g. 'move SRAM closer to compute')"
          className="flex-1 bg-transparent text-sm font-mono text-chip-text placeholder:text-chip-muted focus:outline-none"
          disabled={loading}
        />
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
        {EXAMPLE_COMMANDS.map((cmd) => (
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
