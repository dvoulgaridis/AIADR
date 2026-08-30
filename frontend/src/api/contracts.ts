/** Stable aliases for generated API contracts. */

import type { components } from "./generated/openapi";

export type AnalysisEvent = components["schemas"]["AnalysisEvent"];
export type AnalysisCancelledEvent = components["schemas"]["AnalysisCancelledEvent"];
export type AnalysisCompleteEvent = components["schemas"]["AnalysisCompleteEvent"];
export type AnalysisErrorEvent = components["schemas"]["AnalysisErrorEvent"];
export type AnalysisProgressEvent = components["schemas"]["AnalysisProgressEvent"];
export type ApiFormat = components["schemas"]["ApiFormat"];
export type AuditEvent = components["schemas"]["AuditEvent"];
export type AuditEventsResponse = components["schemas"]["AuditEventsResponse"];
export type ClassificationOption = components["schemas"]["ClassificationOption"];
export type ClassificationOptionsResponse = components["schemas"]["ClassificationOptionsResponse"];
export type AudioRange = components["schemas"]["AudioRange"];
export type AudioTarget = components["schemas"]["AudioTarget"];
export type DocumentTarget = components["schemas"]["DocumentTarget"];
export type DocumentLocator = components["schemas"]["DocumentLocator"];
export type DocxTextLocator = components["schemas"]["DocxTextLocator"];
export type DocxStoryKind = components["schemas"]["DocxStoryKind"];
export type DocxTextSelectionRequest = components["schemas"]["DocxTextSelectionRequest"];
export type PlainTextLocator = components["schemas"]["PlainTextLocator"];
export type ErrorResponse = components["schemas"]["ErrorResponse"];
export type ErrorCode = components["schemas"]["ErrorCode"];
export type ErrorPayload = components["schemas"]["ErrorPayload"];
export type ExportCreateResponse = components["schemas"]["ExportCreateResponse"];
export type DependenciesResponse = components["schemas"]["DependenciesResponse"];
export type DependencyStatus = components["schemas"]["DependencyStatus"];
export type FileDescriptor = components["schemas"]["FileDescriptor"];
export type DocumentSource = components["schemas"]["DocumentSource"];
export type DocumentState = components["schemas"]["DocumentState"];
export type DocxDocumentState = components["schemas"]["DocxDocumentState"];
export type Finding = components["schemas"]["Finding"];
export type FindingTarget = components["schemas"]["FindingTarget"];
export type FindingUpdateRequest = components["schemas"]["FindingUpdateRequest"];
export type Layer = components["schemas"]["Layer"];
export type ImageTarget = components["schemas"]["ImageTarget"];
export type ImageSurface = components["schemas"]["ImageSurface"];
export type FileImageSurface = components["schemas"]["FileImageSurface"];
export type PdfPageSurface = components["schemas"]["PdfPageSurface"];
export type DocxPictureSurface = components["schemas"]["DocxPictureSurface"];
export type DocxPicturePlacement = components["schemas"]["DocxPicturePlacement"];
export type DocxPicturePlacementsResponse = components["schemas"]["DocxPicturePlacementsResponse"];
export type InstructionSetCreateRequest = components["schemas"]["InstructionSetCreateRequest"];
export type InstructionSetDefinition = components["schemas"]["InstructionSetDefinition"];
export type InstructionSetPrompts = components["schemas"]["InstructionSetPrompts"];
export type InstructionSetReference = components["schemas"]["InstructionSetReference"];
export type InstructionSetSummary = components["schemas"]["InstructionSetSummary"];
export type InstructionSetsResponse = components["schemas"]["InstructionSetsResponse"];
export type InstructionSetUpdateRequest = components["schemas"]["InstructionSetUpdateRequest"];
export type LayerAction = components["schemas"]["LayerAction"];
export type LayerEffect = components["schemas"]["LayerEffect"];
export type EffectSource = components["schemas"]["EffectSource"];
export type LayersResponse = components["schemas"]["LayersResponse"];
export type LayerUpdateRequest = components["schemas"]["LayerUpdateRequest"];
export type ManualFindingCreateRequest = components["schemas"]["ManualFindingCreateRequest"];
export type DebugModelIO = components["schemas"]["DebugModelIO"];
export type ModelInteractionLog = components["schemas"]["ModelInteractionLog"];
export type ModelRequestSummary = components["schemas"]["ModelRequestSummary"];
export type ModelResultSummary = components["schemas"]["ModelResultSummary"];
export type ParseStatus = components["schemas"]["ParseStatus"];
export type ModelLogsResponse = components["schemas"]["ModelLogsResponse"];
export type ModelMetadata = components["schemas"]["ModelMetadata"];
export type PdfTextLine = components["schemas"]["PdfTextLine"];
export type PdfDocumentState = components["schemas"]["PdfDocumentState"];
export type DocumentTextLinesResponse = components["schemas"]["DocumentTextLinesResponse"];
export type PrivacyCategory = components["schemas"]["PrivacyCategory"];
export type Model = components["schemas"]["Model"];
export type ModelsResponse = components["schemas"]["ModelsResponse"];
export type ModelWriteRequest = components["schemas"]["ModelWriteRequest"];
export type ProviderModelSettings = components["schemas"]["ProviderModelSettings"];
export type ProviderWriteSettings = components["schemas"]["ProviderWriteSettings"];
export type ModelCapabilities = components["schemas"]["ModelCapabilities"];
export type OpenAIOutputTokenParameter = components["schemas"]["OpenAIOutputTokenParameter"];
export type ReviewOptions = components["schemas"]["ReviewOptions"];
export type Session = components["schemas"]["Session"];
export type SessionStatus = components["schemas"]["SessionStatus"];
export type SessionUpdateRequest = components["schemas"]["SessionUpdateRequest"];
export type Source = components["schemas"]["Source"];
export type SourceKind = components["schemas"]["SourceKind"];
export type TargetRegion = components["schemas"]["TargetRegion"];
export type TextDocumentState = components["schemas"]["TextDocumentState"];

export function isImageTarget(target: FindingTarget): target is ImageTarget {
  return target.kind === "image";
}

export function isFileImageTarget(target: FindingTarget): target is ImageTarget & {
  surface: FileImageSurface;
} {
  return isImageTarget(target) && target.surface.type === "file";
}

export function isPdfPageTarget(target: FindingTarget): target is ImageTarget & {
  surface: PdfPageSurface;
} {
  return isImageTarget(target) && target.surface.type === "pdf_page";
}

export function isDocxPictureTarget(target: FindingTarget): target is ImageTarget & {
  surface: DocxPictureSurface;
} {
  return isImageTarget(target) && target.surface.type === "docx_picture";
}

export function isDocumentTarget(target: FindingTarget): target is DocumentTarget {
  return target.kind === "document";
}

export function isPlainTextTarget(target: FindingTarget): target is DocumentTarget & {
  locator: PlainTextLocator;
} {
  return isDocumentTarget(target) && target.locator.format === "text";
}

export function isDocxTextTarget(target: FindingTarget): target is DocumentTarget & {
  locator: DocxTextLocator;
} {
  return isDocumentTarget(target) && target.locator.format === "docx";
}

export function isAudioTarget(target: FindingTarget): target is AudioTarget {
  return target.kind === "audio";
}

export function isDocumentSource(source: Source): source is DocumentSource {
  return source.kind === "document";
}

export function isTextDocumentSource(
  source: Source,
): source is DocumentSource & { state: TextDocumentState } {
  return isDocumentSource(source) && source.state.layout === "text";
}

export function isPdfDocumentSource(
  source: Source,
): source is DocumentSource & { state: PdfDocumentState } {
  return isDocumentSource(source) && source.state.layout === "fixed";
}

export function isDocxDocumentSource(
  source: Source,
): source is DocumentSource & { state: DocxDocumentState } {
  return isDocumentSource(source) && source.state.layout === "word_processing";
}

export function isPaginatedDocumentSource(
  source: Source,
): source is DocumentSource & { state: PdfDocumentState | DocxDocumentState } {
  return isPdfDocumentSource(source) || isDocxDocumentSource(source);
}
