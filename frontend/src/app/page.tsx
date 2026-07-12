"use client";

import { useEffect, useState } from "react";
import Header from "@/components/Header";
import LeftSidebar from "@/components/LeftSidebar";
import RightPanel from "@/components/RightPanel";
import FloorplanCanvas from "@/components/FloorplanCanvas";
import OverlayBar from "@/components/OverlayBar";
import CommandBar from "@/components/CommandBar";
import ImportPanel from "@/components/ImportPanel";
import { useLayoutStore } from "@/store/layoutStore";

export default function EditorPage() {
  const loadExample = useLayoutStore((s) => s.loadExample);
  const loadConfig = useLayoutStore((s) => s.loadConfig);
  const loading = useLayoutStore((s) => s.loading);
  const error = useLayoutStore((s) => s.error);
  const currentLayout = useLayoutStore((s) => s.currentLayout);
  const [importOpen, setImportOpen] = useState(false);

  useEffect(() => {
    loadConfig();
    if (!currentLayout) loadExample();
  }, [loadConfig, loadExample, currentLayout]);

  return (
    <div className="flex h-screen flex-col">
      <Header onImport={() => setImportOpen(true)} />
      {loading && !error && (
        <div className="absolute left-1/2 top-14 z-50 -translate-x-1/2 rounded border border-chip-border bg-chip-panel px-3 py-1 font-mono text-xs text-chip-accent">
          Working…
        </div>
      )}
      <div className="flex min-h-0 flex-1">
        <LeftSidebar />
        <main className="flex min-w-0 flex-1 flex-col">
          <OverlayBar />
          <FloorplanCanvas />
          <CommandBar />
        </main>
        <RightPanel />
      </div>
      {importOpen && <ImportPanel onClose={() => setImportOpen(false)} />}
    </div>
  );
}
