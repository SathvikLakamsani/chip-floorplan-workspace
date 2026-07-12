"use client";

import { useState } from "react";
import Inspector from "./Inspector";
import ReportPanel from "./ReportPanel";
import { useLayoutStore } from "@/store/layoutStore";

export default function RightPanel() {
  const [tab, setTab] = useState<"inspector" | "report">("report");
  const currentLayout = useLayoutStore((s) => s.currentLayout);
  const drcCount = useLayoutStore((s) => s.drc.violations.length);

  if (!currentLayout) return null;

  return (
    <aside className="panel flex w-80 shrink-0 flex-col overflow-hidden">
      <div className="flex items-center gap-1 border-b border-chip-border p-2">
        <button className={`tab-btn ${tab === "report" ? "tab-btn-on" : "tab-btn-off"}`} onClick={() => setTab("report")}>
          EDA Report {drcCount > 0 && <span className="ml-1 text-chip-danger">({drcCount})</span>}
        </button>
        <button className={`tab-btn ${tab === "inspector" ? "tab-btn-on" : "tab-btn-off"}`} onClick={() => setTab("inspector")}>
          Inspector
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        {tab === "report" ? <ReportPanel /> : <Inspector />}
      </div>
    </aside>
  );
}
