"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Header() {
  const pathname = usePathname();

  return (
    <header className="h-12 border-b border-chip-border bg-chip-panel flex items-center px-4 gap-6 shrink-0">
      <div className="flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-chip-accent animate-pulse" />
        <span className="font-mono text-sm font-semibold text-chip-accent">
          Floorplan Workspace
        </span>
        <span className="text-xs text-chip-muted ml-1">MVP</span>
      </div>

      <nav className="flex gap-1 text-sm">
        <Link
          href="/"
          className={`px-3 py-1 rounded ${
            pathname === "/"
              ? "bg-chip-border text-chip-accent"
              : "text-chip-muted hover:text-chip-text"
          }`}
        >
          Editor
        </Link>
        <Link
          href="/compare"
          className={`px-3 py-1 rounded ${
            pathname === "/compare"
              ? "bg-chip-border text-chip-accent"
              : "text-chip-muted hover:text-chip-text"
          }`}
        >
          Compare
        </Link>
      </nav>

      <div className="ml-auto text-xs text-chip-muted font-mono">
        OpenROAD Flow Scripts · Mock Engine
      </div>
    </header>
  );
}
