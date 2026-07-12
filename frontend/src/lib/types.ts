export type BlockType =
  | "compute"
  | "sram"
  | "memory"
  | "noc"
  | "io"
  | "pll"
  | "clock"
  | "controller"
  | "analog"
  | "stdcell"
  | "other";

export type BlockClass =
  | "hard_macro"
  | "soft_logic"
  | "io"
  | "analog"
  | "clock"
  | "memory"
  | "standard_cell_region";

export type Orientation = "N" | "S" | "E" | "W" | "FN" | "FS" | "FE" | "FW";
export type PlacementStatus = "placed" | "fixed" | "unplaced";
export type PinType = "signal" | "clock" | "power" | "ground";
export type PinSide = "left" | "right" | "top" | "bottom";
export type NetType = "signal" | "clock" | "power" | "ground";
export type Severity = "error" | "warning" | "info";

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Halo {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export interface Pin {
  name: string;
  side: PinSide | string;
  offset: number;
  type: PinType | string;
  direction?: string;
}

export interface Chip {
  name: string;
  unit: string;
  die?: Rect | null;
  core?: Rect | null;
  width: number;
  height: number;
}

export interface Block {
  id: string;
  name: string;
  type: BlockType | string;
  class: BlockClass | string;
  x: number;
  y: number;
  width: number;
  height: number;
  fixed: boolean;
  orientation: Orientation | string;
  placement_status: PlacementStatus | string;
  power: number;
  clock_domain: string;
  voltage_domain: string;
  criticality: number;
  halo?: Halo | null;
  keepout: boolean;
  pins: Pin[];
  instance_count?: number;
}

export interface Net {
  id: string;
  name: string;
  source: string;
  sinks: string[];
  width: number;
  criticality: number;
  traffic: number;
  type: NetType | string;
}

export interface Constraint {
  id: string;
  type: string;
  description: string;
  targets: string[];
  priority: string;
  params?: Record<string, unknown>;
}

export interface TimingPath {
  id: string;
  startpoint: string;
  endpoint: string;
  slack: number;
  distance: number;
  criticality: number;
  clock: string;
  explanation: string;
}

export interface CongestionRegion {
  x: number;
  y: number;
  width: number;
  height: number;
  score: number;
  reason: string;
}

export interface PowerRegion {
  x: number;
  y: number;
  width: number;
  height: number;
  density: number;
  reason: string;
}

export interface Metrics {
  wns: number;
  tns: number;
  violating_paths: number;
  wire_length: number;
  congestion_score: number;
  area_utilization: number;
  power_estimate: number;
  drc_count: number;
}

export interface Layout {
  chip: Chip;
  blocks: Block[];
  nets: Net[];
  constraints: Constraint[];
  timing_paths: TimingPath[];
  congestion_regions: CongestionRegion[];
  power_regions: PowerRegion[];
  metrics?: Metrics | null;
}

export interface DRCViolation {
  id: string;
  severity: Severity | string;
  rule: string;
  message: string;
  targets: string[];
  region?: Rect | null;
  suggestion: string;
}

export interface DRCReport {
  violations: DRCViolation[];
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
  overlays: Record<string, boolean>;
  source: "rule" | "llm" | "none";
}

export interface AppConfig {
  llm_enabled: boolean;
  llm_provider: string | null;
  llm_model: string | null;
}

export interface CandidateLayout {
  id: string;
  name: string;
  objective: string;
  layout: Layout;
  explanation: string;
  tradeoff: string;
  metric_deltas: Record<string, number>;
}

export interface AnalyzeResponse {
  layout: Layout;
  metrics: Metrics;
  explanations: string[];
  drc: DRCReport;
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

export interface ImportResponse {
  layout: Layout | null;
  warnings: string[];
  files_found: Record<string, string[]>;
  design_name: string;
  unit_scale: string;
}

export type OverlayKey =
  | "nets"
  | "pins"
  | "timing"
  | "congestion"
  | "power"
  | "powerGrid"
  | "rows"
  | "halos"
  | "labels";

export type OverlayState = Record<OverlayKey, boolean>;
