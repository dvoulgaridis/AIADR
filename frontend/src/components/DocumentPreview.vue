<template>
  <div v-if="isTextDocumentSource(session.source)" class="text-preview-box">
    <div
      ref="textPreviewFrame"
      class="text-preview-frame text-preview-content"
      :class="{ 'creating-target': creatingFinding }"
      @click="selectPlainTextHighlight"
      @pointerup="completePlainTextSelection"
    >
      <div
        v-for="line in renderedTextLines"
        :key="line.lineId"
        class="text-source-line"
        :data-text-line-id="line.lineId"
        v-html="line.html"
      />
    </div>
  </div>
  <div v-else class="pdf-preview-stack">
    <PdfDocumentPreview
      :src="documentPreviewUrl"
      :text-lines="textLines"
      :docx-picture-placements="picturePlacements"
      :highlights="documentHighlights"
      :allow-wrapped-selection="isDocxDocumentSource(session.source)"
      :allow-image-targets="isPdfDocumentSource(session.source)"
      :creating-finding="creatingFinding"
      :editable="editable"
      :layers="layers"
      :selected-layer-id="selectedLayerId"
      @create-target="(target) => emit('create-target', target)"
      @loading-change="setPdfLoading"
      @select-layer="(layerId) => emit('select-layer', layerId)"
      @select-text="completePdfSelection"
      @update-finding="
        (findingId, updates) => emit('update-finding', findingId, updates)
      "
    />
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  defineAsyncComponent,
  nextTick,
  ref,
  watch,
} from "vue";
import { api } from "../api/client";
import type {
  DocumentLocator,
  DocxPicturePlacement,
  FindingTarget,
  FindingUpdateRequest,
  Layer,
  PdfTextLine,
  Session,
} from "../api/contracts";
import {
  isDocumentTarget,
  isDocxDocumentSource,
  isDocxTextTarget,
  isPdfDocumentSource,
  isPlainTextTarget,
  isTextDocumentSource,
} from "../api/contracts";
import { isAbortError } from "../api/errors";
import { errorMessage, useNotificationsStore } from "../stores/notifications";
import { resolveTextReplacements } from "../utils/textReplacements";

const PdfDocumentPreview = defineAsyncComponent(
  () => import("./PdfDocumentPreview.vue"),
);

interface DocumentTextHighlight {
  layerId: string;
  page: number;
  lineId: string;
  text: string;
  occurrence: number;
  usesRenderedText: boolean;
}

const props = defineProps<{
  session: Session;
  layers: Layer[];
  selectedLayerId: string | null;
  creatingFinding: boolean;
  editable: boolean;
  renderedPreviewUrl: string;
}>();
const emit = defineEmits<{
  "update-finding": [findingId: string, updates: FindingUpdateRequest];
  "create-target": [target: FindingTarget];
  "loading-change": [loading: boolean];
  "select-layer": [layerId: string];
}>();
const notifications = useNotificationsStore();
const textLines = ref<PdfTextLine[]>([]);
const picturePlacements = ref<DocxPicturePlacement[]>([]);
const textPreview = ref("");
const textPreviewFrame = ref<HTMLElement | null>(null);
const pdfLoading = ref(false);
const placementsLoading = ref(false);
let evidenceGeneration = 0;
let placementGeneration = 0;

const documentPreviewUrl = computed(() =>
  isDocxDocumentSource(props.session.source)
    ? props.renderedPreviewUrl
    : api.sourceUrl(props.session.session_id),
);
const textReplacements = computed(() => resolveTextReplacements(props.layers));
const textLayers = computed(() =>
  props.layers.filter(
    (layer) =>
      isPlainTextTarget(layer.finding.target) &&
      layer.enabled &&
      layer.action !== "preserve",
  ),
);
const renderedTextLines = computed(() =>
  textPreview.value.split(/\r?\n/).map((text, index) => {
    const lineId = `t${index + 1}`;
    return {
      lineId,
      html: text
        ? renderTextWithLayers(
            text,
            textLayers.value.filter(
              (layer) =>
                isPlainTextTarget(layer.finding.target) &&
                layer.finding.target.locator.line_id === lineId,
            ),
          )
        : "&nbsp;",
      text,
    };
  }),
);
const documentHighlights = computed<DocumentTextHighlight[]>(() =>
  props.layers.flatMap((layer) => {
    const target = layer.finding.target;
    if (
      !layer.enabled ||
      layer.action === "preserve" ||
      !isDocumentTarget(target) ||
      target.locator.format === "text"
    ) {
      return [];
    }

    const locator = target.locator;
    const usesRenderedText =
      isDocxDocumentSource(props.session.source) &&
      layer.finding.review_decision === "confirmed";
    const text = usesRenderedText
      ? textReplacements.value[layer.id] ?? locator.exact_text
      : locator.exact_text;
    const selectedLineIndex = textLines.value.findIndex(
      (line) =>
        line.page === locator.page && line.line_id === locator.line_id,
    );
    const occurrence = usesRenderedText
      ? props.layers.filter((candidate) => {
          if (
            candidate.id === layer.id ||
            !isDocxTextTarget(candidate.finding.target) ||
            candidate.finding.review_decision !== "confirmed" ||
            !candidate.enabled ||
            candidate.action === "preserve" ||
            textReplacements.value[candidate.id] !== text
          ) {
            return false;
          }
          const candidateLocator = candidate.finding.target.locator;
          const candidateLineIndex = textLines.value.findIndex(
            (line) =>
              line.page === candidateLocator.page &&
              line.line_id === candidateLocator.line_id,
          );
          return (
            candidateLocator.page === locator.page &&
            candidateLineIndex >= 0 &&
            candidateLineIndex < selectedLineIndex
          );
        }).length
      : 0;
    return [
      {
        layerId: layer.id,
        page: locator.page,
        lineId: locator.line_id,
        text,
        occurrence,
        usesRenderedText,
      },
    ];
  }),
);

watch(
  () => props.session.session_id,
  (sessionId, _previous, onCleanup) => {
    const generation = ++evidenceGeneration;
    const controller = new AbortController();
    textLines.value = [];
    textPreview.value = "";
    onCleanup(() => controller.abort());

    if (isTextDocumentSource(props.session.source)) {
      void loadPlainTextPreview(sessionId, generation, controller.signal);
    } else {
      void loadTextLines(sessionId, generation, controller.signal);
    }
  },
  { immediate: true },
);

watch(
  [() => props.session.session_id, () => props.renderedPreviewUrl],
  ([sessionId], _previous, onCleanup) => {
    const generation = ++placementGeneration;
    const controller = new AbortController();
    picturePlacements.value = [];
    onCleanup(() => controller.abort());

    if (isDocxDocumentSource(props.session.source)) {
      setPlacementsLoading(true);
      void loadPicturePlacements(sessionId, generation, controller.signal);
    } else {
      picturePlacements.value = [];
      setPlacementsLoading(false);
    }
  },
  { immediate: true },
);

watch(
  [() => props.selectedLayerId, () => textPreview.value],
  async ([layerId]) => {
    if (!layerId || !textPreviewFrame.value) return;
    await nextTick();
    textPreviewFrame.value
      ?.querySelector<HTMLElement>(
        `[data-layer-id="${CSS.escape(layerId)}"]`,
      )
      ?.scrollIntoView({
        block: "nearest",
        inline: "nearest",
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
      });
  },
);

async function loadPlainTextPreview(
  sessionId: string,
  generation: number,
  signal: AbortSignal,
): Promise<void> {
  emit("loading-change", true);
  try {
    const response = await fetch(api.previewUrl(sessionId), { signal });
    if (!response.ok) {
      throw new Error(
        `Text preview request failed with status ${response.status}.`,
      );
    }
    const preview = await response.text();
    if (
      !signal.aborted &&
      generation === evidenceGeneration &&
      props.session.session_id === sessionId
    ) {
      textPreview.value = preview;
    }
  } catch (error) {
    if (!isAbortError(error) && generation === evidenceGeneration) {
      notifications.error(
        errorMessage(error, "Text preview could not be loaded."),
      );
    }
  } finally {
    if (generation === evidenceGeneration) emit("loading-change", false);
  }
}

async function loadTextLines(
  sessionId: string,
  generation: number,
  signal: AbortSignal,
): Promise<void> {
  try {
    const response = await api.getDocumentTextLines(sessionId, signal);
    if (
      !signal.aborted &&
      generation === evidenceGeneration &&
      props.session.session_id === sessionId
    ) {
      textLines.value = response.lines;
    }
  } catch (error) {
    if (!isAbortError(error) && generation === evidenceGeneration) {
      notifications.error(
        errorMessage(error, "Document text could not be loaded."),
      );
    }
  }
}

async function loadPicturePlacements(
  sessionId: string,
  generation: number,
  signal: AbortSignal,
): Promise<void> {
  try {
    const response = await api.getDocxPicturePlacements(sessionId, signal);
    if (
      !signal.aborted &&
      generation === placementGeneration &&
      props.session.session_id === sessionId
    ) {
      picturePlacements.value = response.placements;
    }
  } catch (error) {
    if (!isAbortError(error) && generation === placementGeneration) {
      notifications.error(
        errorMessage(error, "Document picture placements could not be loaded."),
      );
    }
  } finally {
    if (generation === placementGeneration) setPlacementsLoading(false);
  }
}

function setPdfLoading(loading: boolean): void {
  if (pdfLoading.value === loading) return;
  pdfLoading.value = loading;
  emit("loading-change", pdfLoading.value || placementsLoading.value);
}

function setPlacementsLoading(loading: boolean): void {
  if (placementsLoading.value === loading) return;
  placementsLoading.value = loading;
  emit("loading-change", pdfLoading.value || placementsLoading.value);
}

async function completePdfSelection(selection: {
  page: number;
  line_id: string;
  exact_text: string;
}): Promise<void> {
  if (!isDocxDocumentSource(props.session.source)) return;
  try {
    const locator = await api.resolveDocxTextTarget(
      props.session.session_id,
      selection,
    );
    emit("create-target", { kind: "document", locator });
  } catch (error) {
    notifications.error(
      errorMessage(error, "The selected text could not be resolved."),
    );
  }
}

function renderTextWithLayers(text: string, layers: Layer[]): string {
  let rendered = escapeHtml(text);
  for (const layer of layers) {
    const locator = textLocatorFor(layer);
    if (!locator) continue;
    const target = escapeHtml(locator.exact_text);
    const replacement = escapeHtml(
      textReplacements.value[layer.id] ?? locator.exact_text,
    );
    const layerId = escapeHtml(layer.id);
    const markup =
      layer.id === props.selectedLayerId
        ? `<mark class="text-target-highlight selected" data-layer-id="${layerId}">${replacement}</mark>`
        : `<span class="text-target-highlight" data-layer-id="${layerId}">${replacement}</span>`;
    rendered = rendered.replaceAll(target, markup);
  }
  return rendered;
}

function textLocatorFor(layer: Layer): DocumentLocator | null {
  const target = layer.finding.target;
  return isDocumentTarget(target) ? target.locator : null;
}

function selectPlainTextHighlight(event: MouseEvent): void {
  if (props.creatingFinding || hasActiveTextSelection()) return;
  const target = event.target;
  if (!(target instanceof Element)) return;
  const marker = target.closest<HTMLElement>("[data-layer-id]");
  if (!marker || !textPreviewFrame.value?.contains(marker)) return;
  const layerId = marker.dataset.layerId;
  if (layerId) emit("select-layer", layerId);
}

function hasActiveTextSelection(): boolean {
  const selection = window.getSelection();
  return Boolean(selection && !selection.isCollapsed && selection.toString());
}

function completePlainTextSelection(): void {
  if (!props.creatingFinding || !isTextDocumentSource(props.session.source)) {
    return;
  }
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed) {
    notifications.warning("Select text within one source line.");
    return;
  }
  const start = textLineElement(selection.anchorNode);
  const end = textLineElement(selection.focusNode);
  if (!start || start !== end) {
    notifications.warning(
      "Select a continuous fragment within one source line.",
    );
    return;
  }
  const lineId = start.dataset.textLineId;
  const exactText = selection.toString();
  const sourceLine = renderedTextLines.value.find(
    (line) => line.lineId === lineId,
  );
  if (!lineId || !exactText || !sourceLine?.text.includes(exactText)) {
    notifications.error("The selected text could not be matched to the source.");
    return;
  }
  selection.removeAllRanges();
  emit("create-target", {
    kind: "document",
    locator: {
      format: "text",
      line_id: lineId,
      exact_text: exactText,
    },
  });
}

function textLineElement(node: Node | null): HTMLElement | null {
  const element = node instanceof HTMLElement ? node : node?.parentElement;
  return element?.closest<HTMLElement>("[data-text-line-id]") ?? null;
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
</script>
