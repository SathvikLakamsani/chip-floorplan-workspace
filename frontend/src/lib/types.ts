export type BlockType =
  | "compute"
  | "sram"
  | "noc"
  | "io"
  | "pll"
  | "controller"
  | "other";

export interface Chip {
  name: string;
  width: number;
  height: number;
  unit: string;
}

export interface Block {
  id: string;
  name: string;
  type: BlockType | string;
  x: number;
  y: number;
  width: number;
  height: number;
  fixed: boolean;
  power: number;
  clock_domain: string;
  voltage_domain: string;
  criticality: number;
}

export interface Net {
  id: string;
  source: string;
  sinks: string[];
  width: number;
  criticality: number;
  traffic: number;
}

export interface Constraint {
  id: string;
  type: string;
  description: string;
  targets: string[];
  priority: string;
}

export interface Metrics {
  wns: number;
  tns: number;
  wire_length: number;
  congestion_score: number;
  area_utilization: number;
  power_estimate: number;
}

export interface Layout {
  chip: Chip;
  blocks: Block[];
  nets: Net[];
  constraints: Constraint[];
  metrics?: Metrics | null;
}

export interface CommandAction {
  type: string;
  targets: string[];
  reason: string;
  params?: Record<string, unknown>;
}

export interface CommandResponse {
  actions: CommandAction[];
  preview_layout: Layout | null;
  expected_metric_delta: Record<string, number>;
  explanation: string;
}

export interface CandidateLayout {
  id: string;
  name: string;
  layout: Layout;
  explanation: string;
  metric_deltas: Record<string, number>;
}

export interface AnalyzeResponse {
  layout: Layout;
  metrics: Metrics;
  explanations: string[];
}

export interface GenerateCandidatesResponse {
  baseline: Layout;
  candidates: CandidateLayout[];
}

export interface ExportResponse {
  format: string;
  content: string;
  filename: string;
}
