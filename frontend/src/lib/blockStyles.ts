import type { Block } from "./types";

export interface BlockStyle {
  fill: string;
  stroke: string;
  glow: string;
  label: string;
}

// Color by functional type; visual treatment (solid/dashed) by class.
const TYPE_COLORS: Record<string, { fill: string; stroke: string; label: string }> = {
  compute: { fill: "#0e2a3a", stroke: "#00b4d8", label: "COMPUTE" },
  sram: { fill: "#2a1e3a", stroke: "#a06be0", label: "MEMORY" },
  memory: { fill: "#2a1e3a", stroke: "#a06be0", label: "MEMORY" },
  noc: { fill: "#0e3226", stroke: "#00e5a0", label: "NoC" },
  controller: { fill: "#33240e", stroke: "#ffb020", label: "CTRL" },
  pll: { fill: "#3a1420", stroke: "#ff6b81", label: "CLOCK" },
  clock: { fill: "#3a1420", stroke: "#ff6b81", label: "CLOCK" },
  io: { fill: "#1a1f2a", stroke: "#6b7c93", label: "IO" },
  analog: { fill: "#2a2410", stroke: "#d4af37", label: "ANALOG" },
  stdcell: { fill: "#141b26", stroke: "#3a4a5f", label: "STD CELLS" },
  other: { fill: "#161d28", stroke: "#4a5a6f", label: "LOGIC" },
};

export function blockType(b: Block): string {
  return typeof b.type === "string" ? b.type : String(b.type);
}

export function blockClass(b: Block): string {
  return typeof b.class === "string" ? b.class : String(b.class);
}

export function getBlockStyle(b: Block): BlockStyle {
  const t = blockType(b);
  const c = TYPE_COLORS[t] ?? TYPE_COLORS.other;
  return { fill: c.fill, stroke: c.stroke, glow: c.stroke, label: c.label };
}

export function isHardMacro(b: Block): boolean {
  const c = blockClass(b);
  return c === "hard_macro" || c === "memory" || c === "clock" || c === "analog";
}

export function isSoftLogic(b: Block): boolean {
  const c = blockClass(b);
  return c === "soft_logic" || c === "standard_cell_region";
}

export const PIN_COLORS: Record<string, string> = {
  signal: "#00e5a0",
  clock: "#ff6b81",
  power: "#ffb020",
  ground: "#6b7c93",
};

export function netColor(criticality: number, type: string): string {
  if (type === "clock") return "#ff6b81";
  if (type === "power") return "#ffb020";
  if (type === "ground") return "#6b7c93";
  if (criticality >= 0.9) return "#ff4757";
  if (criticality >= 0.75) return "#ffb020";
  if (criticality >= 0.6) return "#00b4d8";
  return "#3a5a7a";
}

// Congestion score -> translucent heat color.
export function congestionColor(score: number): string {
  if (score >= 0.8) return "rgba(255,71,87,0.42)";
  if (score >= 0.65) return "rgba(255,120,60,0.38)";
  if (score >= 0.5) return "rgba(255,176,32,0.32)";
  return "rgba(255,215,64,0.22)";
}

export function powerColor(density: number): string {
  if (density >= 0.8) return "rgba(255,71,87,0.40)";
  if (density >= 0.6) return "rgba(255,140,50,0.34)";
  if (density >= 0.4) return "rgba(255,196,60,0.26)";
  return "rgba(120,200,255,0.18)";
}
