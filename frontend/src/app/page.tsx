"use client";

import { useEffect } from "react";
import Header from "@/components/Header";
import LeftSidebar from "@/components/LeftSidebar";
import RightInspector from "@/components/RightInspector";
import FloorplanCanvas from "@/components/FloorplanCanvas";
import CommandBar from "@/components/CommandBar";
import { useLayoutStore } from "@/store/layoutStore";

export default function EditorPage() {
  const loadExample = useLayoutStore((s) => s.loadExample);
  const loadConfig = useLayoutStore((s) => s.loadConfig);
  const loading = useLayoutStore((s) => s.loading);
  const error = useLayoutStore((s) => s.error);

  useEffect(() => {
    loadConfig();
    loadExample();
  }, [loadConfig, loadExample]);

  return (
    <div className="h-screen flex flex-col">
      <Header />
      {loading && !error && (
        <div className="absolute top-14 left-1/2 -translate-x-1/2 z-50 px-3 py-1 rounded bg-chip-panel border border-chip-border text-xs text-chip-accent font-mono">
          Loading...
        </div>
      )}
      <div className="flex flex-1 min-h-0">
        <LeftSidebar />
        <main className="flex-1 flex flex-col min-w-0">
          <FloorplanCanvas />
          <CommandBar />
        </main>
        <RightInspector />
      </div>
    </div>
  );
}
