"use client";

import { useState } from "react";
import { useLayoutStore } from "@/store/layoutStore";

const SAMPLE_PATH = "../examples/openroad_run";

export default function ImportPanel({ onClose }: { onClose: () => void }) {
  const [path, setPath] = useState(SAMPLE_PATH);
  const importRun = useLayoutStore((s) => s.importRun);
  const loading = useLayoutStore((s) => s.loading);
  const importInfo = useLayoutStore((s) => s.importInfo);
  const sourceMode = useLayoutStore((s) => s.sourceMode);
  const error = useLayoutStore((s) => s.error);

  const handleImport = async () => {
    if (!path.trim()) return;
    await importRun(path.trim());
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="panel w-full max-w-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-chip-border px-4 py-3">
          <h2 className="font-mono text-sm text-chip-accent">Import OpenROAD / OpenLane Run</h2>
          <button onClick={onClose} className="text-chip-muted hover:text-chip-text">✕</button>
        </div>

        <div className="space-y-4 p-4">
          <p className="text-xs leading-relaxed text-chip-muted">
            Run OpenROAD, ORFS, or OpenLane separately, then paste the path to the
            run directory. The app scans it offline for DEF / LEF / metrics /
            timing / congestion files and reconstructs the floorplan. It does not
            execute OpenROAD.
          </p>

          <div>
            <label className="text-[10px] uppercase tracking-wider text-chip-muted">Run directory path</label>
            <div className="mt-1 flex gap-2">
              <input
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder="/path/to/openroad_or_openlane_run"
                className="flex-1 rounded border border-chip-border bg-chip-bg px-3 py-2 font-mono text-xs text-chip-text focus:border-chip-accent focus:outline-none"
              />
              <button
                onClick={handleImport}
                disabled={loading}
                className="rounded bg-chip-accent px-4 py-2 text-xs font-semibold text-chip-bg hover:opacity-90 disabled:opacity-50"
              >
                {loading ? "Importing…" : "Import"}
              </button>
            </div>
            <button onClick={() => setPath(SAMPLE_PATH)} className="mt-1 text-[10px] text-chip-accent2 hover:underline">
              Use bundled sample run
            </button>
          </div>

          {error && (
            <div className="rounded border border-chip-danger/40 bg-chip-danger/10 px-3 py-2 text-xs text-chip-danger">
              {error}
            </div>
          )}

          {importInfo && (
            <div className="space-y-3 rounded border border-chip-border bg-chip-bg p-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-mono text-sm text-chip-accent">{importInfo.design_name || "—"}</div>
                  <div className="text-[10px] text-chip-muted">Units: {importInfo.unit_scale || "unknown"}</div>
                </div>
                {sourceMode === "imported" && (
                  <button onClick={onClose} className="rounded bg-chip-accent2/20 px-3 py-1.5 text-xs text-chip-accent2 border border-chip-accent2/30 hover:bg-chip-accent2/30">
                    View on canvas →
                  </button>
                )}
              </div>

              <div className="grid grid-cols-5 gap-2">
                {(["def", "lef", "metrics", "timing_reports", "congestion_reports"] as const).map((k) => {
                  const n = importInfo.files_found[k]?.length ?? 0;
                  return (
                    <div key={k} className={`rounded border px-2 py-1.5 text-center ${n > 0 ? "border-chip-accent/40 bg-chip-accent/5" : "border-chip-border"}`}>
                      <div className={`font-mono text-sm ${n > 0 ? "text-chip-accent" : "text-chip-muted"}`}>{n}</div>
                      <div className="text-[9px] text-chip-muted">{k.replace("_reports", "")}</div>
                    </div>
                  );
                })}
              </div>

              {importInfo.warnings.length > 0 && (
                <div>
                  <div className="mb-1 text-[10px] uppercase tracking-wider text-chip-muted">Parser warnings</div>
                  <ul className="max-h-32 space-y-1 overflow-y-auto scrollbar-thin">
                    {importInfo.warnings.map((w, i) => (
                      <li key={i} className="text-[10px] leading-snug text-chip-warn">• {w}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
