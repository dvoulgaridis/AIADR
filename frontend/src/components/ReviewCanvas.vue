<template>
  <section
    class="panel preview-panel"
    :class="{ 'preview-busy': previewBusy }"
    :aria-busy="previewBusy"
  >
    <div class="preview-content">
      <div v-if="!session" class="audio-placeholder">
        Upload a file to create a local review session.
      </div>
      <div v-else-if="session.source.kind === 'audio'" class="audio-placeholder">
        <AudioWaveform
          :src="renderedPreviewUrl"
          :layers="layers"
          :selected-layer-id="selectedLayerId"
          :creating-finding="creatingFinding"
          :editable="editable"
          @create-target="(target) => emit('create-target', target)"
          @loading-change="setAudioPreviewLoading"
          @select-layer="(layerId) => emit('select-layer', layerId)"
          @update-finding="
            (findingId, updates) => emit('update-finding', findingId, updates)
          "
        />
      </div>
      <DocumentPreview
        v-else-if="session.source.kind === 'document'"
        :key="session.session_id"
        :session="session"
        :layers="layers"
        :selected-layer-id="selectedLayerId"
        :creating-finding="creatingFinding"
        :editable="editable"
        :rendered-preview-url="renderedPreviewUrl"
        @create-target="(target) => emit('create-target', target)"
        @loading-change="setDocumentPreviewLoading"
        @select-layer="(layerId) => emit('select-layer', layerId)"
        @update-finding="
          (findingId, updates) => emit('update-finding', findingId, updates)
        "
      />
      <div v-else class="canvas-box" :style="canvasStyle">
        <img
          v-if="displayedImageUrl"
          class="source-preview"
          alt="Uploaded source preview"
          :src="displayedImageUrl"
        />
        <ImageRegionLayer
          :layers="layers"
          :selected-layer-id="selectedLayerId"
          :creating-finding="creatingFinding"
          :editable="editable"
          :surface="fileImageSurface"
          :show-effects="false"
          @create-target="
            (region) =>
              emit('create-target', {
                kind: 'image',
                surface: fileImageSurface,
                region,
              })
          "
          @select-layer="(layerId) => emit('select-layer', layerId)"
          @update-finding="
            (findingId, updates) => emit('update-finding', findingId, updates)
          "
        />
      </div>
    </div>
    <LoadingSpinner
      v-if="previewBusy"
      class="preview-loading"
      :label="previewLoadingLabel"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { api } from "../api/client";
import type {
  FindingTarget,
  FindingUpdateRequest,
  Layer,
  Session,
} from "../api/contracts";
import {
  isDocxDocumentSource,
  isDocxPictureTarget,
  isDocxTextTarget,
  isFileImageTarget,
} from "../api/contracts";
import { isAbortError } from "../api/errors";
import { useNotificationsStore } from "../stores/notifications";
import AudioWaveform from "./AudioWaveform.vue";
import DocumentPreview from "./DocumentPreview.vue";
import ImageRegionLayer from "./ImageRegionLayer.vue";
import LoadingSpinner from "./LoadingSpinner.vue";

const props = defineProps<{
  session: Session | null;
  layers: Layer[];
  selectedLayerId: string | null;
  analyzing: boolean;
  creatingFinding: boolean;
  editable: boolean;
}>();
const emit = defineEmits<{
  "update-finding": [findingId: string, updates: FindingUpdateRequest];
  "create-target": [target: FindingTarget];
  "select-layer": [layerId: string];
}>();
const notifications = useNotificationsStore();
const fileImageSurface = { type: "file" as const };
const previewRevision = ref(0);
const sourceLoading = ref(false);
const previewSize = ref<{ width: number; height: number } | null>(null);
const displayedImageUrl = ref("");
let imageLoadGeneration = 0;
let imageLoadController: AbortController | null = null;
let previewRenderSessionId = props.session?.session_id ?? null;

const previewUrl = computed(() =>
  props.session ? api.previewUrl(props.session.session_id) : "",
);
const renderedPreviewUrl = computed(
  () => `${previewUrl.value}?revision=${previewRevision.value}`,
);
const previewBusy = computed(() => props.analyzing || sourceLoading.value);
const previewLoadingLabel = computed(() =>
  props.analyzing ? "Analyzing source" : "Loading preview",
);
const canvasStyle = computed(() => {
  const source = props.session?.source;
  if (source?.kind !== "image") return {};
  const width = source.width || previewSize.value?.width;
  const height = source.height || previewSize.value?.height;
  return width && height ? { aspectRatio: `${width} / ${height}` } : {};
});
const previewRenderState = computed(() => {
  const source = props.session?.source;
  if (!source) return "";

  return props.layers
    .filter((layer) => {
      const target = layer.finding.target;
      if (source.kind === "image") return isFileImageTarget(target);
      if (source.kind === "audio") return target.kind === "audio";
      if (isDocxDocumentSource(source)) {
        return isDocxTextTarget(target) || isDocxPictureTarget(target);
      }
      return false;
    })
    .sort((left, right) => left.id.localeCompare(right.id))
    .map((layer) =>
      JSON.stringify({
        id: layer.id,
        target: layer.finding.target,
        reviewDecision: layer.finding.review_decision,
        action: layer.action,
        effect: layer.effect,
        enabled: layer.enabled,
        fillColor: layer.fill_color,
        customText: layer.custom_text,
      }),
    )
    .join("|");
});

watch(
  () => props.session?.session_id,
  () => {
    previewRevision.value = 0;
    previewSize.value = null;
    clearDisplayedImage();
    sourceLoading.value = props.session !== null;
  },
  { immediate: true },
);
watch(
  [() => props.session?.session_id, renderedPreviewUrl],
  ([sessionId, requestedUrl], _previous, onCleanup) => {
    const generation = ++imageLoadGeneration;
    const session = props.session;
    if (!sessionId || session?.source.kind !== "image") return;

    imageLoadController?.abort();
    const controller = new AbortController();
    imageLoadController = controller;
    sourceLoading.value = true;
    onCleanup(() => controller.abort());
    void stageImagePreview(sessionId, requestedUrl, generation, controller);
  },
  { immediate: true },
);
watch([() => props.session?.session_id, previewRenderState], ([sessionId]) => {
  if (sessionId !== previewRenderSessionId) {
    previewRenderSessionId = sessionId ?? null;
    return;
  }
  previewRevision.value += 1;
});

onBeforeUnmount(() => {
  imageLoadGeneration += 1;
  imageLoadController?.abort();
  clearDisplayedImage();
});

async function stageImagePreview(
  sessionId: string,
  requestedUrl: string,
  generation: number,
  controller: AbortController,
): Promise<void> {
  let objectUrl = "";
  try {
    const response = await fetch(requestedUrl, { signal: controller.signal });
    if (!response.ok) {
      throw new Error(`Image preview request failed with status ${response.status}.`);
    }
    objectUrl = URL.createObjectURL(await response.blob());
    const image = new Image();
    image.src = objectUrl;
    await image.decode();
    if (
      generation !== imageLoadGeneration ||
      props.session?.session_id !== sessionId
    ) {
      return;
    }

    const previousUrl = displayedImageUrl.value;
    displayedImageUrl.value = objectUrl;
    objectUrl = "";
    previewSize.value = {
      width: image.naturalWidth,
      height: image.naturalHeight,
    };
    sourceLoading.value = false;
    await nextTick();
    if (previousUrl) URL.revokeObjectURL(previousUrl);
  } catch (error) {
    if (
      !isAbortError(error) &&
      generation === imageLoadGeneration &&
      props.session?.session_id === sessionId
    ) {
      sourceLoading.value = false;
      notifications.error("Image preview could not be loaded.");
    }
  } finally {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    if (imageLoadController === controller) imageLoadController = null;
  }
}

function clearDisplayedImage(): void {
  if (displayedImageUrl.value) URL.revokeObjectURL(displayedImageUrl.value);
  displayedImageUrl.value = "";
}

function setAudioPreviewLoading(loading: boolean): void {
  if (props.session?.source.kind === "audio") sourceLoading.value = loading;
}

function setDocumentPreviewLoading(loading: boolean): void {
  if (props.session?.source.kind === "document") {
    sourceLoading.value = loading;
  }
}
</script>
