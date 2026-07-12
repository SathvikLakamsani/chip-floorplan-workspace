import type {
  AnalyzeResponse,
  AppConfig,
  CommandResponse,
  ExportResponse,
  GenerateCandidatesResponse,
  ImportResponse,
  Layout,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function getConfig(): Promise<AppConfig> {
  return fetchApi<AppConfig>("/api/config");
}

export async function getExampleLayout(): Promise<Layout> {
  return fetchApi<Layout>("/api/layouts/example");
}

export async function analyzeLayout(layout: Layout): Promise<AnalyzeResponse> {
  return fetchApi<AnalyzeResponse>("/api/layouts/analyze", {
    method: "POST",
    body: JSON.stringify(layout),
  });
}

export async function parseCommand(
  command: string,
  layout: Layout
): Promise<CommandResponse> {
  const body = { command, layout };
  return fetchApi<CommandResponse>("/api/layouts/command", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function applyActions(
  layout: Layout,
  actions: CommandResponse["actions"]
): Promise<Layout> {
  const body = { layout, actions };
  return fetchApi<Layout>("/api/layouts/apply", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function generateCandidates(
  layout: Layout
): Promise<GenerateCandidatesResponse> {
  return fetchApi<GenerateCandidatesResponse>(
    "/api/layouts/generate-candidates",
    {
      method: "POST",
      body: JSON.stringify(layout),
    }
  );
}

export async function exportLayout(
  layout: Layout,
  format: "json" | "tcl" | "def" = "json"
): Promise<ExportResponse> {
  return fetchApi<ExportResponse>("/api/layouts/export", {
    method: "POST",
    body: JSON.stringify({ layout, format }),
  });
}

export async function importOpenROAD(path: string): Promise<ImportResponse> {
  return fetchApi<ImportResponse>("/api/import/openroad", {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}
