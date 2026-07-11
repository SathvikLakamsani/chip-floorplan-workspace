"use client";

import type { BlockType } from "@/lib/types";

const BLOCK_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  compute: { bg: "#0d3320", border: "#00e5a0", text: "#00e5a0" },
  sram: { bg: "#0a2540", border: "#00b4d8", text: "#00b4d8" },
  noc: { bg: "#2a1a40", border: "#a855f7", text: "#c084fc" },
  io: { bg: "#2a2010", border: "#ffb020", text: "#ffb020" },
  pll: { bg: "#2a1020", border: "#ff4757", text: "#ff6b81" },
  controller: { bg: "#1a2a30", border: "#48dbfb", text: "#48dbfb" },
  other: { bg: "#1a2030", border: "#6b7c93", text: "#6b7c93" },
};

export function getBlockColors(type: BlockType | string) {
  return BLOCK_COLORS[type] || BLOCK_COLORS.other;
}

interface BlockNodeProps {
  data: {
    label: string;
    blockType: string;
    fixed: boolean;
    criticality: number;
    width: number;
    height: number;
  };
  selected?: boolean;
}

export function BlockNode({ data, selected }: BlockNodeProps) {
  const colors = getBlockColors(data.blockType);

  return (
    <div
      className="relative flex flex-col items-center justify-center rounded border-2 transition-shadow"
      style={{
        width: data.width,
        height: data.height,
        backgroundColor: colors.bg,
        borderColor: selected ? "#ffffff" : colors.border,
        boxShadow: selected
          ? `0 0 12px ${colors.border}80`
          : `0 0 4px ${colors.border}40`,
        opacity: data.fixed ? 0.85 : 1,
      }}
    >
      {data.fixed && (
        <div className="absolute top-1 right-1 text-[8px] text-chip-warn">🔒</div>
      )}
      <span
        className="text-[10px] font-mono font-semibold text-center px-1 leading-tight"
        style={{ color: colors.text }}
      >
        {data.label}
      </span>
      <span className="text-[8px] text-chip-muted mt-0.5 uppercase">
        {data.blockType}
      </span>
    </div>
  );
}
