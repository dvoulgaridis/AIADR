<template>
  <div
    ref="host"
    class="pdf-document-viewer"
    :class="{ 'creating-text-target': creatingFinding && !allowImageTargets }"
  >
    <div class="pdf-zoom-controls" aria-label="Document zoom controls">
      <button type="button" aria-label="Zoom out" :disabled="zoom <= MIN_ZOOM" @click="setZoom(zoom - ZOOM_STEP)">−</button>
      <output class="pdf-zoom-level">{{ Math.round(zoom * 100) }}%</output>
      <button type="button" aria-label="Zoom in" :disabled="zoom >= MAX_ZOOM" @click="setZoom(zoom + ZOOM_STEP)">+</button>
      <button type="button" aria-label="Fit page width" :class="{ active: fitWidth }" :aria-pressed="fitWidth" @click="fitPageWidth">↔</button>
    </div>
    <div
      ref="scrollHost"
      class="pdf-page-scroll"
      @click="selectTextHighlightAtPoint"
      @pointerup="completeSelection"
    >
      <div v-for="page in pages" :key="page" class="pdf-page" :data-page="page">
        <canvas />
        <ImageRegionLayer
          v-if="allowImageTargets"
          :layers="layers"
          :selected-layer-id="selectedLayerId"
          :creating-finding="creatingFinding"
          :editable="editable"
          :surface="surfaceForPage(page)"
          :pixelated-previews="pixelatedPreviews"
          @create-target="(region) => emit('create-target', { kind: 'image', surface: surfaceForPage(page), region })"
          @select-layer="(layerId) => emit('select-layer', layerId)"
          @update-finding="(findingId, updates) => emit('update-finding', findingId, updates)"
        />
        <div
          v-for="placement in placementsForPage(page)"
          :key="placement.occurrence_id"
          class="docx-picture-placement"
          :data-occurrence-id="placement.occurrence_id"
          :style="placementStyle(placement)"
        >
          <ImageRegionLayer
            :layers="layers"
            :selected-layer-id="selectedLayerId"
            :creating-finding="creatingFinding"
            :editable="editable"
            :surface="surfaceForPicture(placement.occurrence_id)"
            :allow-rotation="false"
            :coordinate-rotation-degrees="placement.region.rotation_degrees"
            :show-effects="false"
            @create-target="(region) => emit('create-target', { kind: 'image', surface: surfaceForPicture(placement.occurrence_id), region })"
            @select-layer="(layerId) => emit('select-layer', layerId)"
            @update-finding="(findingId, updates) => emit('update-finding', findingId, updates)"
          />
        </div>
        <div class="pdf-target-highlight-layer" aria-hidden="true" />
        <div class="textLayer" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  getDocument,
  GlobalWorkerOptions,
  TextLayer,
  type PDFDocumentLoadingTask,
  type PDFDocumentProxy,
  type RenderTask,
} from "pdfjs-dist/legacy/build/pdf.mjs";
import workerUrl from "pdfjs-dist/legacy/build/pdf.worker.min.mjs?url";
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type {
  FindingTarget,
  FindingUpdateRequest,
  DocxPicturePlacement,
  DocxPictureSurface,
  Layer,
  PdfPageSurface,
  PdfTextLine,
} from "../api/contracts";
import { renderPixelatedRegion } from "../utils/imageEffects";
import { isDocxPictureTarget, isPdfPageTarget } from "../api/contracts";
import { useNotificationsStore } from "../stores/notifications";
import ImageRegionLayer from "./ImageRegionLayer.vue";

GlobalWorkerOptions.workerSrc = workerUrl;

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 2.5;
const ZOOM_STEP = 0.1;

interface DocumentTextHighlight {
  layerId: string;
  page: number;
  lineId: string;
  text: string;
  occurrence: number;
  usesRenderedText: boolean;
}

const props = defineProps<{
  src: string;
  textLines: PdfTextLine[];
  docxPicturePlacements: DocxPicturePlacement[];
  highlights: DocumentTextHighlight[];
  allowWrappedSelection: boolean;
  allowImageTargets: boolean;
  creatingFinding: boolean;
  editable: boolean;
  layers: Layer[];
  selectedLayerId: string | null;
}>();
const emit = defineEmits<{
  "create-target": [target: FindingTarget];
  "loading-change": [loading: boolean];
  "select-layer": [layerId: string];
  "select-text": [selection: { page: number; line_id: string; exact_text: string }];
  "update-finding": [findingId: string, updates: FindingUpdateRequest];
}>();

const host = ref<HTMLElement | null>(null);
const scrollHost = ref<HTMLElement | null>(null);
const pages = ref<number[]>([]);
const notifications = useNotificationsStore();
const zoom = ref(1);
const fitWidth = ref(true);
const pixelatedPreviews = ref<Record<string, string>>({});
let loadingTask: PDFDocumentLoadingTask | null = null;
let activeLoadingTask: PDFDocumentLoadingTask | null = null;
let pdfDocument: PDFDocumentProxy | null = null;
let renderTasks = new Set<RenderTask>();
let textLayers = new Set<TextLayer>();
let resizeObserver: ResizeObserver | null = null;
let documentGeneration = 0;
let renderGeneration = 0;

watch(() => props.src, () => void loadDocument(), { immediate: true });
watch(
  [() => props.highlights, () => props.textLines],
  async () => {
    await nextTick();
    renderHighlights(false);
  },
);
watch(
  () => props.layers
    .filter((layer) => isPdfPageTarget(layer.finding.target))
    .map((layer) => (
      `${layer.id}:${JSON.stringify(layer.finding.target)}:${layer.finding.review_decision}:`
      + `${layer.action}:${layer.effect}:${layer.enabled}`
    ))
    .join("|"),
  async () => {
    await nextTick();
    buildPixelatedPreviews();
  },
);
watch(
  () => props.selectedLayerId,
  async () => {
    await nextTick();
    renderHighlights(true);
    scrollSelectedImageIntoView();
  },
);

onMounted(() => {
  resizeObserver = new ResizeObserver(() => {
    if (fitWidth.value) void renderPages();
  });
  if (host.value) resizeObserver.observe(host.value);
});

onBeforeUnmount(() => {
  documentGeneration += 1;
  resizeObserver?.disconnect();
  cancelRendering();
  void loadingTask?.destroy();
  void activeLoadingTask?.destroy();
});

function cancelRendering() {
  renderGeneration += 1;
  for (const task of renderTasks) task.cancel();
  for (const layer of textLayers) layer.cancel();
  renderTasks = new Set();
  textLayers = new Set();
}

async function loadDocument() {
  const expectedDocument = ++documentGeneration;
  cancelRendering();
  const obsoleteTask = loadingTask;
  loadingTask = null;
  await obsoleteTask?.destroy();
  if (expectedDocument !== documentGeneration) return;
  if (!props.src) return;
  emit("loading-change", true);
  try {
    const task = getDocument({ url: props.src });
    loadingTask = task;
    const loaded = await task.promise;
    if (expectedDocument !== documentGeneration) {
      await task.destroy();
      return;
    }
    loadingTask = null;
    pdfDocument = loaded;
    pages.value = Array.from({ length: loaded.numPages }, (_, index) => index + 1);
    await nextTick();
    await renderPages(expectedDocument, true);
    if (expectedDocument === documentGeneration) {
      const previousTask = activeLoadingTask;
      activeLoadingTask = task;
      await previousTask?.destroy();
    } else {
      await task.destroy();
    }
  } catch (cause) {
    if (expectedDocument === documentGeneration && !isRenderingCancellation(cause)) {
      notifications.error(cause instanceof Error ? cause.message : "PDF preview failed.");
    }
  } finally {
    if (expectedDocument === documentGeneration) {
      loadingTask = null;
      emit("loading-change", false);
    }
  }
}

async function renderPages(
  expectedDocument = documentGeneration,
  navigateToHighlight = false,
) {
  const pdf = pdfDocument;
  const container = scrollHost.value;
  if (!pdf || !container) return;
  cancelRendering();
  const expectedRender = renderGeneration;
  try {
    for (const pageNumber of pages.value) {
      if (expectedDocument !== documentGeneration || expectedRender !== renderGeneration) return;
      const pageElement = container.querySelector<HTMLElement>(`.pdf-page[data-page="${pageNumber}"]`);
      const canvas = pageElement?.querySelector<HTMLCanvasElement>("canvas");
      const textLayerHost = pageElement?.querySelector<HTMLElement>(".textLayer");
      if (!pageElement || !canvas || !textLayerHost) continue;

      const page = await pdf.getPage(pageNumber);
      if (expectedDocument !== documentGeneration || expectedRender !== renderGeneration) return;
      const baseViewport = page.getViewport({ scale: 1 });
      const availableWidth = Math.max(container.clientWidth - 32, 1);
      const viewport = page.getViewport({ scale: (availableWidth / baseViewport.width) * zoom.value });
      const pixelRatio = window.devicePixelRatio || 1;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("Canvas rendering is not available.");

      pageElement.style.width = `${viewport.width}px`;
      pageElement.style.height = `${viewport.height}px`;
      pageElement.style.setProperty(
        "--total-scale-factor",
        `${viewport.scale * viewport.userUnit}`,
      );
      pageElement.style.setProperty("--scale-round-x", "1px");
      pageElement.style.setProperty("--scale-round-y", "1px");
      canvas.width = Math.floor(viewport.width * pixelRatio);
      canvas.height = Math.floor(viewport.height * pixelRatio);
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      textLayerHost.replaceChildren();

      const renderTask = page.render({
        canvas,
        canvasContext: context,
        viewport,
        transform: pixelRatio === 1 ? undefined : [pixelRatio, 0, 0, pixelRatio, 0, 0],
      });
      renderTasks.add(renderTask);
      const textLayer = new TextLayer({
        textContentSource: await page.getTextContent(),
        container: textLayerHost,
        viewport,
      });
      textLayers.add(textLayer);
      await Promise.all([renderTask.promise, textLayer.render()]);
      renderTasks.delete(renderTask);
      textLayers.delete(textLayer);
    }
    renderHighlights(navigateToHighlight);
    buildPixelatedPreviews();
    if (navigateToHighlight) scrollSelectedImageIntoView();
  } catch (cause) {
    if (
      expectedDocument === documentGeneration
      && expectedRender === renderGeneration
      && !isRenderingCancellation(cause)
    ) {
      notifications.error(cause instanceof Error ? cause.message : "PDF page rendering failed.");
    }
  }
}

function isRenderingCancellation(cause: unknown): boolean {
  return cause instanceof Error && (
    cause.name === "RenderingCancelledException" || cause.name === "AbortException"
  );
}

function setZoom(value: number) {
  fitWidth.value = false;
  zoom.value = Math.round(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value)) * 100) / 100;
  void renderPages();
}

function surfaceForPage(page: number): PdfPageSurface {
  return { type: "pdf_page", page };
}

function surfaceForPicture(occurrenceId: string): DocxPictureSurface {
  return { type: "docx_picture", occurrence_id: occurrenceId };
}

function placementsForPage(page: number): DocxPicturePlacement[] {
  return props.docxPicturePlacements.filter((placement) => placement.page === page);
}

function placementStyle(placement: DocxPicturePlacement) {
  const region = placement.region;
  return {
    left: `${region.x * 100}%`,
    top: `${region.y * 100}%`,
    width: `${region.width * 100}%`,
    height: `${region.height * 100}%`,
    transform: `rotate(${region.rotation_degrees}deg)`,
  };
}

function buildPixelatedPreviews() {
  const container = scrollHost.value;
  if (!container) return;
  const next: Record<string, string> = {};
  for (const layer of props.layers) {
    const target = layer.finding.target;
    if (
      !isPdfPageTarget(target)
      || layer.finding.review_decision !== "confirmed"
      || !layer.enabled
      || layer.action === "preserve"
      || layer.effect !== "pixelate"
    ) continue;
    const source = container.querySelector<HTMLCanvasElement>(
      `.pdf-page[data-page="${target.surface.page}"] > canvas`,
    );
    if (!source?.width || !source.height) continue;
    const preview = renderPixelatedRegion(
      source,
      source.width,
      source.height,
      target.region,
    );
    if (preview) next[layer.id] = preview;
  }
  pixelatedPreviews.value = next;
}

function scrollSelectedImageIntoView() {
  const container = scrollHost.value;
  const layer = props.layers.find((candidate) => candidate.id === props.selectedLayerId);
  if (!container || !layer) return;
  const target = layer.finding.target;
  const pageNumber = isPdfPageTarget(target)
    ? target.surface.page
    : props.docxPicturePlacements.find(
        (placement) =>
          isDocxPictureTarget(target)
          && placement.occurrence_id === target.surface.occurrence_id,
      )?.page;
  if (!pageNumber) return;
  const page = container.querySelector<HTMLElement>(`.pdf-page[data-page="${pageNumber}"]`);
  const selected = isDocxPictureTarget(target)
    ? page?.querySelector<HTMLElement>(
        `.docx-picture-placement[data-occurrence-id="${target.surface.occurrence_id}"] .overlay.selected`,
      )
    : page?.querySelector<HTMLElement>(".overlay.selected");
  if (selected) scrollHighlightIntoView(container, [selected]);
}

interface MappedCharacter {
  node: Text;
  start: number;
  end: number;
  value: string;
}

function normalizedText(value: string): string {
  return [...value.normalize("NFKC").toLocaleLowerCase()]
    .filter((character) => !/\s/u.test(character))
    .join("");
}

function mappedText(root: HTMLElement): MappedCharacter[] {
  const characters: MappedCharacter[] = [];
  const walker = window.document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    const textNode = node as Text;
    for (let start = 0; start < textNode.data.length;) {
      const codePoint = textNode.data.codePointAt(start);
      if (codePoint === undefined) break;
      const sourceCharacter = String.fromCodePoint(codePoint);
      const end = start + sourceCharacter.length;
      for (const value of sourceCharacter.normalize("NFKC").toLocaleLowerCase()) {
        if (!/\s/u.test(value)) characters.push({ node: textNode, start, end, value });
      }
      start = end;
    }
    node = walker.nextNode();
  }
  return characters;
}

function occurrenceStarts(value: string, target: string): number[] {
  return sequenceStarts([...value], [...target]);
}

function sequenceStarts(value: string[], target: string[]): number[] {
  const starts: number[] = [];
  if (!target.length || target.length > value.length) return starts;
  for (let index = 0; index <= value.length - target.length; index += 1) {
    if (target.every((character, offset) => value[index + offset] === character)) {
      starts.push(index);
    }
  }
  return starts;
}

function rangeForText(
  root: HTMLElement,
  value: string,
  occurrence: number,
): Range | null {
  const characters = mappedText(root);
  const target = [...normalizedText(value)];
  if (!characters.length || !target.length) return null;
  const starts = sequenceStarts(characters.map((character) => character.value), target);
  const start = starts[occurrence];
  if (start === undefined) return null;
  const first = characters[start];
  const last = characters[start + target.length - 1];
  if (!first || !last) return null;
  const range = window.document.createRange();
  range.setStart(first.node, first.start);
  range.setEnd(last.node, last.end);
  return range;
}

function lineOccurrence(line: PdfTextLine): number {
  const target = normalizedText(line.text);
  let occurrence = 0;
  for (const candidate of props.textLines) {
    if (candidate.page !== line.page) continue;
    if (candidate.line_id === line.line_id) return occurrence;
    occurrence += occurrenceStarts(normalizedText(candidate.text), target).length;
  }
  return occurrence;
}

function sourceTextOccurrence(highlight: DocumentTextHighlight): number {
  const target = normalizedText(highlight.text);
  let occurrence = 0;
  for (const line of props.textLines) {
    if (line.page !== highlight.page) continue;
    if (line.line_id === highlight.lineId) return occurrence;
    occurrence += occurrenceStarts(normalizedText(line.text), target).length;
  }
  return highlight.occurrence;
}

function clearHighlights() {
  scrollHost.value
    ?.querySelectorAll<HTMLElement>(".pdf-target-highlight-layer")
    .forEach((layer) => layer.replaceChildren());
}

function hasActiveTextSelection(): boolean {
  const selection = window.getSelection();
  return Boolean(selection && !selection.isCollapsed && selection.toString());
}

function selectTextHighlightAtPoint(event: MouseEvent) {
  if (props.creatingFinding || hasActiveTextSelection()) return;
  const target = event.target;
  if (!(target instanceof Element) || target.closest(".image-region-layer")) return;
  const pageElement = target.closest<HTMLElement>(".pdf-page");
  if (!pageElement) return;

  const matches = [...pageElement.querySelectorAll<HTMLElement>(".pdf-target-highlight")]
    .filter((marker) => {
      const bounds = marker.getBoundingClientRect();
      return (
        event.clientX >= bounds.left
        && event.clientX <= bounds.right
        && event.clientY >= bounds.top
        && event.clientY <= bounds.bottom
      );
    });
  const marker = matches[matches.length - 1];
  const layerId = marker?.dataset.layerId;
  if (!marker || !layerId) return;

  emit("select-layer", layerId);
}

function scrollHighlightIntoView(container: HTMLElement, markers: HTMLElement[]) {
  const bounds = markers.map((marker) => marker.getBoundingClientRect());
  if (!bounds.length) return;
  const containerBounds = container.getBoundingClientRect();
  const centerY = (Math.min(...bounds.map((item) => item.top))
    + Math.max(...bounds.map((item) => item.bottom))) / 2;
  const centerX = (Math.min(...bounds.map((item) => item.left))
    + Math.max(...bounds.map((item) => item.right))) / 2;
  const top = container.scrollTop + centerY - containerBounds.top - (container.clientHeight / 2);
  const left = container.scrollLeft + centerX - containerBounds.left - (container.clientWidth / 2);
  container.scrollTo({
    top: Math.max(0, Math.min(top, container.scrollHeight - container.clientHeight)),
    left: Math.max(0, Math.min(left, container.scrollWidth - container.clientWidth)),
    behavior: "smooth",
  });
}

function renderHighlights(navigate: boolean) {
  clearHighlights();
  const container = scrollHost.value;
  if (!container) return;
  const selectedLayerId = props.selectedLayerId;
  const highlights = [...props.highlights].sort(
    (left, right) =>
      Number(left.layerId === selectedLayerId) - Number(right.layerId === selectedLayerId),
  );

  for (const highlight of highlights) {
    const page = container.querySelector<HTMLElement>(
      `.pdf-page[data-page="${highlight.page}"]`,
    );
    const textLayer = page?.querySelector<HTMLElement>(".textLayer");
    const highlightLayer = page?.querySelector<HTMLElement>(".pdf-target-highlight-layer");
    if (!page || !textLayer || !highlightLayer) continue;

    const sourceLine = props.textLines.find(
      (line) => line.page === highlight.page && line.line_id === highlight.lineId,
    );
    const occurrence = highlight.usesRenderedText
      ? highlight.occurrence
      : sourceTextOccurrence(highlight);
    const range = rangeForText(textLayer, highlight.text, occurrence)
      ?? (sourceLine ? rangeForText(textLayer, sourceLine.text, lineOccurrence(sourceLine)) : null);
    if (!range) continue;

    const pageBounds = page.getBoundingClientRect();
    for (const bounds of range.getClientRects()) {
      if (!bounds.width || !bounds.height) continue;
      const marker = window.document.createElement("span");
      marker.className = "pdf-target-highlight";
      marker.classList.toggle("selected", highlight.layerId === selectedLayerId);
      marker.dataset.layerId = highlight.layerId;
      marker.style.left = `${bounds.left - pageBounds.left}px`;
      marker.style.top = `${bounds.top - pageBounds.top}px`;
      marker.style.width = `${bounds.width}px`;
      marker.style.height = `${bounds.height}px`;
      highlightLayer.append(marker);
    }
  }

  if (navigate && selectedLayerId) {
    const markers = [...container.querySelectorAll<HTMLElement>(".pdf-target-highlight")]
      .filter((marker) => marker.dataset.layerId === selectedLayerId);
    scrollHighlightIntoView(container, markers);
  }
}

function fitPageWidth() {
  fitWidth.value = true;
  zoom.value = 1;
  void renderPages();
}

function normalizeSelection(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function selectionLine(
  page: number,
  exactText: string,
  occurrence: number,
): PdfTextLine | null {
  const characters: Array<{ line: PdfTextLine; value: string }> = [];
  for (const line of props.textLines) {
    if (line.page !== page) continue;
    for (const value of normalizedText(line.text)) characters.push({ line, value });
  }
  const target = [...normalizedText(exactText)];
  const starts = sequenceStarts(characters.map((character) => character.value), target);
  const start = starts[occurrence];
  if (start === undefined) return null;
  const matched = characters.slice(start, start + target.length);
  const line = matched[0]?.line;
  if (!line) return null;
  const lineIds = new Set(matched.map((character) => character.line.line_id));
  if (lineIds.size > 1 && !props.allowWrappedSelection) return null;
  const startsOnLine = starts.filter(
    (candidate) => characters[candidate]?.line.line_id === line.line_id,
  );
  return startsOnLine.length === 1 ? line : null;
}

function selectionOccurrence(
  selection: Selection,
  textLayer: HTMLElement,
  exactText: string,
): number | null {
  if (!selection.rangeCount) return null;
  const range = selection.getRangeAt(0);
  if (
    !textLayer.contains(range.startContainer) ||
    !textLayer.contains(range.endContainer)
  ) {
    return null;
  }
  const prefix = window.document.createRange();
  prefix.selectNodeContents(textLayer);
  prefix.setEnd(range.startContainer, range.startOffset);
  const selectedStart = normalizedText(prefix.toString()).length;
  const characters = mappedText(textLayer).map((character) => character.value);
  const starts = sequenceStarts(characters, [...normalizedText(exactText)]);
  const occurrence = starts.indexOf(selectedStart);
  return occurrence >= 0 ? occurrence : null;
}

function completeSelection() {
  if (!props.creatingFinding || props.allowImageTargets || !scrollHost.value) return;
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !selection.anchorNode || !selection.focusNode) return;
  const startPage = selectionPage(selection.anchorNode);
  const endPage = selectionPage(selection.focusNode);
  if (!startPage || startPage !== endPage) {
    notifications.warning("Select a continuous fragment within one PDF page.");
    return;
  }

  const exactText = normalizeSelection(selection.toString());
  const matchingLines = props.textLines.filter(
    (line) => line.page === startPage && normalizeSelection(line.text).includes(exactText),
  );
  let line = matchingLines.length === 1 ? matchingLines[0] : null;
  if (!line && exactText) {
    const page = scrollHost.value.querySelector<HTMLElement>(
      `.pdf-page[data-page="${startPage}"]`,
    );
    const textLayer = page?.querySelector<HTMLElement>(".textLayer");
    const occurrence = textLayer
      ? selectionOccurrence(selection, textLayer, exactText)
      : null;
    line = occurrence === null
      ? null
      : selectionLine(startPage, exactText, occurrence);
  }
  if (!exactText || !line) {
    notifications.warning(
      props.allowWrappedSelection
        ? "Select a unique continuous fragment within one line or adjacent wrapped lines."
        : "Select a unique continuous fragment within one extracted line.",
    );
    return;
  }
  selection.removeAllRanges();
  emit("select-text", {
    page: startPage,
    line_id: line.line_id,
    exact_text: exactText,
  });
}

function selectionPage(node: Node): number | null {
  const element = node instanceof HTMLElement ? node : node.parentElement;
  const page = element?.closest<HTMLElement>(".pdf-page")?.dataset.page;
  return page ? Number(page) : null;
}
</script>
