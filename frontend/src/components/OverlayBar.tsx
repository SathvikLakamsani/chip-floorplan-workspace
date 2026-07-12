"use client";

import { useLayoutStore } from "@/store/layoutStore";
import type { OverlayKey } from "@/lib/types";

const OVERLAYS: { key: OverlayKey; label: string }[] = [
  { key: "nets", label: "Nets" },
  { key: "pins", label: "Pins" },
  { key: "timing", label: "Timing" },
  { key: "congestion", label: "Congestion" },
  { key: "power", label: "Power" },
  { key: "powerGrid", label: "Power Grid" },
  { key: "rows", label: "Rows" },
  { key: "halos", label: "Halos" },
  { key: "labels", label: "Labels" },
];

export default function OverlayBar() {
  const overlays = useLayoutStore((s) => s.overlays);
  const toggleOverlay = useLayoutStore((s) => s.toggleOverlay);

  return (
    <div className="flex flex-wrap items-center gap-1.5 border-b border-chip-border bg-chip-panel/60 px-3 py-2">
      <span className="mr-1 font-mono text-[10px] uppercase tracking-wider text-chip-muted">
        Overlays
      </span>
      {OVERLAYS.map((o) => {
        const on = overlays[o.key];
        return (
          <button
            key={o.key}
            className={`overlay-chip ${on ? "overlay-chip-on" : "overlay-chip-off"}`}
            onClick={() => toggleOverlay(o.key)}
          >
            <span
              className={`h-2 w-2 rounded-full ${on ? "bg-chip-accent" : "bg-chip-border"}`}
            />
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
