<template>
  <section class="panel findings-panel">
    <div class="findings-panel-head">
      <h2>Findings</h2>
      <button
        type="button"
        class="header-add-button new-finding-button"
        aria-label="Add finding"
        :disabled="!classificationOptions.length || !allowNewFinding"
        @click="$emit('new-finding')"
      >
        <span aria-hidden="true">+</span>
      </button>
    </div>
    <div ref="body" class="findings-panel-body">
      <p v-if="!layers.length" class="muted">No findings yet.</p>
      <article
        v-for="layer in layers"
        :key="layer.id"
        :data-layer-id="layer.id"
        class="list-item finding-entry"
        :class="{ active: layer.id === selectedLayerId }"
        role="button"
        tabindex="0"
        @click="selectLayer(layer.id)"
        @keydown="handleEntryKeydown($event, layer.id)"
      >
        <div class="finding-title">{{ findingTitle(layer.finding) }}</div>
        <dl class="finding-meta">
          <div><dt>Privacy</dt><dd>{{ layer.finding.privacy_category }}</dd></div>
          <div><dt>Special</dt><dd>{{ layer.finding.special_category_type }}</dd></div>
          <div><dt>Subject</dt><dd>{{ layer.finding.data_subject_context }}</dd></div>
          <div><dt>Risk</dt><dd>{{ layer.finding.privacy_risk }}</dd></div>
          <div><dt>Origin</dt><dd>{{ layer.finding.created_by || layer.finding.origin }}</dd></div>
          <div v-if="layer.finding.detection_confidence !== null">
            <dt>Confidence</dt>
            <dd>{{ Math.round(layer.finding.detection_confidence * 100) }}%</dd>
          </div>
          <div><dt>Edited</dt><dd>{{ layer.finding.edited ? "yes" : "no" }}</dd></div>
        </dl>
        <p><span>Description:</span> {{ layer.finding.description || "n/a" }}</p>
        <p><span>Reason:</span> {{ layer.finding.reason || "n/a" }}</p>
        <ReviewActionControls
          :finding="layer.finding"
          :layer="layer"
          :review-options="reviewOptions"
          :classification-options="classificationOptions"
          :disabled="!allowEditReview"
          @update-finding="forwardFindingUpdate"
          @update-layer="forwardLayerUpdate"
        />
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import type {
  ClassificationOption,
  Finding,
  FindingUpdateRequest,
  Layer,
  LayerUpdateRequest,
  ReviewOptions,
} from "../api/contracts";
import ReviewActionControls from "./ReviewActionControls.vue";

const props = defineProps<{
  layers: Layer[];
  allowNewFinding: boolean;
  allowEditReview: boolean;
  selectedLayerId: string | null;
  reviewOptions: ReviewOptions | null;
  classificationOptions: ClassificationOption[];
}>();
const body = ref<HTMLElement | null>(null);
const emit = defineEmits<{
  "new-finding": [];
  "select-layer": [layerId: string];
  "update-finding": [findingId: string, updates: FindingUpdateRequest];
  "update-layer": [layerId: string, updates: LayerUpdateRequest];
}>();

function findingTitle(finding: Finding): string {
  const parts = [finding.label, finding.effective_entity_type];
  if (finding.detection_confidence !== null) {
    parts.push(`(${Math.round(finding.detection_confidence * 100)}%)`);
  }
  parts.push(finding.created_by || finding.origin);
  return parts.join(" · ");
}

function selectLayer(layerId: string) {
  emit("select-layer", layerId);
}

function handleEntryKeydown(event: KeyboardEvent, layerId: string): void {
  if (event.target !== event.currentTarget || (event.key !== "Enter" && event.key !== " ")) {
    return;
  }
  event.preventDefault();
  selectLayer(layerId);
}

watch(
  () => props.selectedLayerId,
  async (layerId) => {
    if (!layerId) return;
    await nextTick();
    const entry = body.value?.querySelector<HTMLElement>(
      `[data-layer-id="${CSS.escape(layerId)}"]`,
    );
    entry?.scrollIntoView({
      block: "nearest",
      inline: "nearest",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
  },
  { immediate: true },
);

function forwardFindingUpdate(findingId: string, updates: FindingUpdateRequest) {
  emit("update-finding", findingId, updates);
}

function forwardLayerUpdate(layerId: string, updates: LayerUpdateRequest) {
  emit("update-layer", layerId, updates);
}
</script>
