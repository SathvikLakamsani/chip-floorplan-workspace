import { create } from "zustand";
import type {
  CandidateLayout,
  CommandAction,
  CommandResponse,
  Layout,
  Metrics,
} from "@/lib/types";
import {
  analyzeLayout,
  applyActions,
  exportLayout,
  generateCandidates,
  getExampleLayout,
  parseCommand,
} from "@/lib/api";

interface LayoutHistoryEntry {
  layout: Layout;
  label: string;
  timestamp: number;
}

interface LayoutStore {
  baseline: Layout | null;
  currentLayout: Layout | null;
  selectedBlockId: string | null;
  candidates: CandidateLayout[];
  history: LayoutHistoryEntry[];
  historyIndex: number;
  loading: boolean;
  error: string | null;
  pendingCommand: CommandResponse | null;
  explanations: string[];

  loadExample: () => Promise<void>;
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
}

const MAX_HISTORY = 20;

export const useLayoutStore = create<LayoutStore>((set, get) => ({
  baseline: null,
  currentLayout: null,
  selectedBlockId: null,
  candidates: [],
  history: [],
  historyIndex: -1,
  loading: false,
  error: null,
  pendingCommand: null,
  explanations: [],

  loadExample: async () => {
    set({ loading: true, error: null });
    try {
      const layout = await getExampleLayout();
      const analyzed = await analyzeLayout(layout);
      const entry: LayoutHistoryEntry = {
        layout: analyzed.layout,
        label: "Baseline",
        timestamp: Date.now(),
      };
      set({
        baseline: analyzed.layout,
        currentLayout: analyzed.layout,
        history: [entry],
        historyIndex: 0,
        explanations: analyzed.explanations,
        loading: false,
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
        loading: false,
      });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  submitCommand: async (command) => {
    const { currentLayout } = get();
    if (!currentLayout) return;
    set({ loading: true, error: null, pendingCommand: null });
    try {
      const response = await parseCommand(command, currentLayout);
      if (response.actions.length === 0) {
        set({ error: response.explanation, loading: false, pendingCommand: null });
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
      const updated = await applyActions(
        currentLayout,
        pendingCommand.actions
      );
      const analyzed = await analyzeLayout(updated);
      get().pushHistory("Command applied");
      set({
        currentLayout: analyzed.layout,
        explanations: analyzed.explanations,
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
      set({ candidates: result.candidates, loading: false });
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
      const blob = new Blob([result.content], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = result.filename;
      a.click();
      URL.revokeObjectURL(url);
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
