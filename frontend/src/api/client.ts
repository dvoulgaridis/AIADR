import type {
  AuditEventsResponse,
  ClassificationOptionsResponse,
  DependenciesResponse,
  DocxTextLocator,
  DocxTextSelectionRequest,
  DocxPicturePlacementsResponse,
  ErrorResponse,
  ExportCreateResponse,
  FindingUpdateRequest,
  InstructionSetCreateRequest,
  InstructionSetDefinition,
  InstructionSetsResponse,
  InstructionSetUpdateRequest,
  LayersResponse,
  LayerUpdateRequest,
  ManualFindingCreateRequest,
  ModelMetadata,
  ModelLogsResponse,
  DocumentTextLinesResponse,
  ModelsResponse,
  ModelWriteRequest,
  ReviewOptions,
  Session,
  SessionUpdateRequest,
} from "./contracts";
import { ApiError } from "./errors";

export const API_BASE = "/api/v1";

async function parseError(response: Response): Promise<ApiError> {
  return new ApiError((await response.json()) as ErrorResponse);
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  const headers = init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" };
  const response = await fetch(`${API_BASE}${path}`, { headers, ...init });
  if (!response.ok) throw await parseError(response);
  return response;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await send(path, init)).json() as Promise<T>;
}

async function requestEmpty(path: string, init?: RequestInit): Promise<void> {
  await send(path, init);
}

export const api = {
  listInstructionSets: () => request<InstructionSetsResponse>("/instruction-sets"),
  getInstructionSet: (instructionSetId: string) =>
    request<InstructionSetDefinition>(`/instruction-sets/${instructionSetId}`),
  createInstructionSet: (definition: InstructionSetCreateRequest) =>
    request<string>("/instruction-sets", {
      method: "POST",
      body: JSON.stringify(definition),
    }),
  updateInstructionSet: (instructionSetId: string, definition: InstructionSetUpdateRequest) =>
    requestEmpty(`/instruction-sets/${instructionSetId}`, {
      method: "PUT",
      body: JSON.stringify(definition),
    }),
  deleteInstructionSet: (instructionSetId: string) =>
    requestEmpty(`/instruction-sets/${instructionSetId}`, { method: "DELETE" }),
  activateInstructionSet: (instructionSetId: string) =>
    requestEmpty(`/instruction-sets/${instructionSetId}/active`, { method: "PUT" }),
  listModels: () => request<ModelsResponse>("/settings/models"),
  getDependencies: () => request<DependenciesResponse>("/settings/dependencies"),
  getModelModelMetadata: (modelId: string) =>
    request<ModelMetadata>(`/settings/models/${modelId}/model-metadata`),
  getReviewOptions: (signal?: AbortSignal) =>
    request<ReviewOptions>("/settings/review-options", { signal }),
  putModel: (modelId: string, settings: ModelWriteRequest) =>
    requestEmpty(`/settings/models/${modelId}`, {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
  deleteModel: (modelId: string) =>
    requestEmpty(`/settings/models/${modelId}`, { method: "DELETE" }),
  activateModel: (modelId: string) =>
    requestEmpty(`/settings/models/${modelId}/active`, { method: "PUT" }),
  uploadFile: async (file: File): Promise<string> => {
    const form = new FormData();
    form.append("file", file);
    return request<string>("/uploads", { method: "POST", body: form });
  },
  listSessions: () => request<Session[]>("/sessions"),
  getSession: (sessionId: string, signal?: AbortSignal) =>
    request<Session>(`/sessions/${sessionId}`, { signal }),
  updateSession: (sessionId: string, updates: SessionUpdateRequest) =>
    requestEmpty(`/sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify(updates),
    }),
  deleteSession: (sessionId: string) =>
    requestEmpty(`/sessions/${sessionId}`, { method: "DELETE" }),
  requestAnalysis: (sessionId: string) =>
    requestEmpty(`/sessions/${sessionId}/analysis`, {
      method: "POST",
    }),
  createExport: (sessionId: string) =>
    request<ExportCreateResponse>(`/sessions/${sessionId}/export`, { method: "POST" }),
  addFinding: (sessionId: string, finding: ManualFindingCreateRequest) =>
    request<string>(`/sessions/${sessionId}/findings`, {
      method: "POST",
      body: JSON.stringify(finding),
    }),
  updateFinding: (sessionId: string, findingId: string, updates: FindingUpdateRequest) =>
    requestEmpty(`/sessions/${sessionId}/findings/${findingId}`, {
      method: "PATCH",
      body: JSON.stringify(updates),
    }),
  getLayers: (sessionId: string, signal?: AbortSignal) =>
    request<LayersResponse>(`/sessions/${sessionId}/layers`, { signal }),
  getClassificationOptions: (sessionId: string, signal?: AbortSignal) =>
    request<ClassificationOptionsResponse>(
      `/sessions/${sessionId}/classification-options`,
      { signal },
    ),
  getDocumentTextLines: (sessionId: string, signal?: AbortSignal) =>
    request<DocumentTextLinesResponse>(
      `/sessions/${sessionId}/document/text-lines`,
      { signal },
    ),
  getDocxPicturePlacements: (sessionId: string, signal?: AbortSignal) =>
    request<DocxPicturePlacementsResponse>(
      `/sessions/${sessionId}/document/docx/picture-placements`,
      { signal },
    ),
  resolveDocxTextTarget: (sessionId: string, selection: DocxTextSelectionRequest) =>
    request<DocxTextLocator>(`/sessions/${sessionId}/document/docx/target`, {
      method: "POST",
      body: JSON.stringify(selection),
    }),
  getModelLogs: (sessionId: string, signal?: AbortSignal) =>
    request<ModelLogsResponse>(`/sessions/${sessionId}/model-log`, { signal }),
  getAuditEvents: (sessionId: string, signal?: AbortSignal) =>
    request<AuditEventsResponse>(`/sessions/${sessionId}/audit-events`, { signal }),
  updateLayer: (sessionId: string, layerId: string, updates: LayerUpdateRequest) =>
    requestEmpty(`/sessions/${sessionId}/layers/${layerId}`, {
      method: "PUT",
      body: JSON.stringify(updates),
    }),
  resetEffectOverride: (sessionId: string, layerId: string) =>
    requestEmpty(`/sessions/${sessionId}/layers/${layerId}/effect-override`, {
      method: "DELETE",
    }),
  sourceUrl: (sessionId: string) => `${API_BASE}/sessions/${sessionId}/source`,
  previewUrl: (sessionId: string) => `${API_BASE}/sessions/${sessionId}/preview`,
  exportUrl: (sessionId: string) => `${API_BASE}/sessions/${sessionId}/export/latest`,
};
