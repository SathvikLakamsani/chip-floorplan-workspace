import { create } from "zustand";
import type {
  AppConfig,
  CandidateLayout,
  CommandResponse,
  DRCReport,
  Layout,
  OverlayKey,
  OverlayState,
} from "@/lib/types";
import {
  analyzeLayout,
  applyActions,
  exportLayout,
  generateCandidates,
  getConfig,
  getExampleLayout,
  importOpenROAD,
  parseCommand,
} from "@/lib/api";

interface LayoutHistoryEntry {
  layout: Layout;
  label: string;
  timestamp: number;
}

export interface ImportInfo {
  design_name: string;
  unit_scale: string;
  warnings: string[];
  files_found: Record<string, string[]>;
}

const DEFAULT_OVERLAYS: OverlayState = {
  nets: true,
  pins: false,
  timing: false,
  congestion: false,
  power: false,
  powerGrid: false,
  rows: true,
  halos: true,
  labels: true,
};

interface LayoutStore {
  baseline: Layout | null;
  currentLayout: Layout | null;
  selectedBlockId: string | null;
  candidates: CandidateLayout[];
  history: LayoutHistoryEntry[];
  historyIndex: number;
  loading: boolean;
  error: string | null;
  notice: string | null;
  pendingCommand: CommandResponse | null;
  explanations: string[];
  drc: DRCReport;
  config: AppConfig | null;
  overlays: OverlayState;
  sourceMode: "demo" | "imported";
  importInfo: ImportInfo | null;

  loadConfig: () => Promise<void>;
  loadExample: () => Promise<void>;
  importRun: (path: string) => Promise<void>;
  setSelectedBlock: (id: string | null) => void;
  updateBlock: (blockId: string, updates: Partial<Layout["blocks"][0]>) => void;
  moveBlock: (blockId: string, x: number, y: number) => void;
  analyze: () => Promise<void>;
  submitCommand: (command: string) => Promise<void>;
  applyPendingCommand: () => Promise<void>;
  cancelPendingCommand: () => void;
  undo: () => void;
  generateCandidates: () => Promise<void>;
  loadCandidate: (candidateId: string) => void;
  exportCurrent: (format?: "json" | "tcl" | "def") => Promise<void>;
  pushHistory: (label: string) => void;
  toggleOverlay: (key: OverlayKey) => void;
  setOverlays: (partial: Partial<OverlayState>) => void;
  clearNotice: () => void;
}

const MAX_HISTORY = 20;
const emptyDrc: DRCReport = { violations: [] };

export const useLayoutStore = create<LayoutStore>((set, get) => ({
  baseline: null,
  currentLayout: null,
  selectedBlockId: null,
  candidates: [],
  history: [],
  historyIndex: -1,
  loading: false,
  error: null,
  notice: null,
  pendingCommand: null,
  explanations: [],
  drc: emptyDrc,
  config: null,
  overlays: DEFAULT_OVERLAYS,
  sourceMode: "demo",
  importInfo: null,

  loadConfig: async () => {
    try {
      const config = await getConfig();
      set({ config });
    } catch {
      set({ config: { llm_enabled: false, llm_provider: null, llm_model: null } });
    }
  },

  loadExample: async () => {
    set({ loading: true, error: null });
    try {
      const layout = await getExampleLayout();
      const analyzed = await analyzeLayout(layout);
      set({
        baseline: analyzed.layout,
        currentLayout: analyzed.layout,
        history: [{ layout: analyzed.layout, label: "Baseline", timestamp: Date.now() }],
        historyIndex: 0,
        explanations: analyzed.explanations,
        drc: analyzed.drc,
        loading: false,
        sourceMode: "demo",
        candidates: [],
      });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  importRun: async (path) => {
    set({ loading: true, error: null });
    try {
      const resp = await importOpenROAD(path);
      if (!resp.layout) {
        set({
          error: resp.warnings.join(" ") || "Import failed.",
          loading: false,
          importInfo: {
            design_name: resp.design_name,
            unit_scale: resp.unit_scale,
            warnings: resp.warnings,
            files_found: resp.files_found,
          },
        });
        return;
      }
      const analyzed = await analyzeLayout(resp.layout);
      set({
        baseline: analyzed.layout,
        currentLayout: analyzed.layout,
        history: [{ layout: analyzed.layout, label: "Imported", timestamp: Date.now() }],
        historyIndex: 0,
        explanations: analyzed.explanations,
        drc: analyzed.drc,
        loading: false,
        sourceMode: "imported",
        candidates: [],
        selectedBlockId: null,
        importInfo: {
          design_name: resp.design_name,
          unit_scale: resp.unit_scale,
          warnings: resp.warnings,
          files_found: resp.files_found,
        },
        notice: `Imported ${resp.design_name} (${resp.layout.blocks.length} blocks).`,
      });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  setSelectedBlock: (id) => set({ selectedBlockId: id }),

  updateBlock: (blockId, updates) => {
    const { currentLayout } = get();
    if (!currentLayout) return;
    const blocks = currentLayout.blocks.map((b) =>
      b.id === blockId ? { ...b, ...updates } : b
    );
    set({ currentLayout: { ...currentLayout, blocks } });
  },

  moveBlock: (blockId, x, y) => {
    const { currentLayout } = get();
    if (!currentLayout) return;
    const block = currentLayout.blocks.find((b) => b.id === blockId);
    if (!block || block.fixed) return;
    get().updateBlock(blockId, { x, y });
  },

  analyze: async () => {
    const { currentLayout } = get();
    if (!currentLayout) return;
    set({ loading: true });
    try {
      const result = await analyzeLayout(currentLayout);
      set({
        currentLayout: result.layout,
        explanations: result.explanations,
        drc: result.drc,
        loading: false,
      });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  submitCommand: async (command) => {
    const { currentLayout } = get();
    if (!currentLayout) return;
    set({ loading: true, error: null, pendingCommand: null, notice: null });
    try {
      const response = await parseCommand(command, currentLayout);

      // Overlay-only commands: apply toggles immediately, no preview.
      if (
        response.overlays &&
        Object.keys(response.overlays).length > 0 &&
        response.actions.length === 0
      ) {
        get().setOverlays(response.overlays as Partial<OverlayState>);
        set({ loading: false, notice: response.explanation });
        return;
      }

      // Explain-only / no-op commands: surface the explanation.
      if (response.actions.length === 0) {
        set({
          loading: false,
          pendingCommand: null,
          notice: response.source === "none" ? null : response.explanation,
          error: response.source === "none" ? response.explanation : null,
        });
        return;
      }

      if (response.actions[0]?.type === "generate_candidates") {
        set({ pendingCommand: null, loading: false });
        await get().generateCandidates();
        return;
      }

      set({ pendingCommand: response, loading: false });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  applyPendingCommand: async () => {
    const { pendingCommand, currentLayout } = get();
    if (!pendingCommand || !currentLayout) return;
    set({ loading: true });
    try {
      const updated = await applyActions(currentLayout, pendingCommand.actions);
      const analyzed = await analyzeLayout(updated);
      get().pushHistory("Command applied");
      set({
        currentLayout: analyzed.layout,
        explanations: analyzed.explanations,
        drc: analyzed.drc,
        pendingCommand: null,
        loading: false,
      });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  cancelPendingCommand: () => set({ pendingCommand: null }),

  undo: () => {
    const { history, historyIndex } = get();
    if (historyIndex <= 0) return;
    const newIndex = historyIndex - 1;
    set({
      historyIndex: newIndex,
      currentLayout: history[newIndex].layout,
      selectedBlockId: null,
    });
  },

  generateCandidates: async () => {
    const { currentLayout } = get();
    if (!currentLayout) return;
    set({ loading: true });
    try {
      const result = await generateCandidates(currentLayout);
      set({ candidates: result.candidates, loading: false, notice: "Generated 3 candidates — open the Compare tab." });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  loadCandidate: (candidateId) => {
    const { candidates } = get();
    const candidate = candidates.find((c) => c.id === candidateId);
    if (!candidate) return;
    get().pushHistory(`Loaded ${candidate.name}`);
    set({ currentLayout: candidate.layout, selectedBlockId: null });
  },

  exportCurrent: async (format = "json") => {
    const { currentLayout } = get();
    if (!currentLayout) return;
    try {
      const result = await exportLayout(currentLayout, format);
      const blob = new Blob([result.content], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = result.filename;
      a.click();
      URL.revokeObjectURL(url);
      set({ notice: `Exported ${result.filename}` });
    } catch (e) {
      set({ error: String(e) });
    }
  },

  pushHistory: (label) => {
    const { currentLayout, history, historyIndex } = get();
    if (!currentLayout) return;
    const trimmed = history.slice(0, historyIndex + 1);
    trimmed.push({
      layout: JSON.parse(JSON.stringify(currentLayout)),
      label,
      timestamp: Date.now(),
    });
    if (trimmed.length > MAX_HISTORY) trimmed.shift();
    set({ history: trimmed, historyIndex: trimmed.length - 1 });
  },

  toggleOverlay: (key) =>
    set((s) => ({ overlays: { ...s.overlays, [key]: !s.overlays[key] } })),

  setOverlays: (partial) =>
    set((s) => ({ overlays: { ...s.overlays, ...partial } })),

  clearNotice: () => set({ notice: null }),
}));

export function formatMetricDelta(value: number, decimals = 3): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(decimals)}`;
}

export function metricColor(value: number, invert = false): string {
  const good = invert ? value < 0 : value > 0;
  if (Math.abs(value) < 0.001) return "text-chip-muted";
  return good ? "text-chip-accent" : "text-chip-danger";
}
