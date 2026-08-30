<template>
  <fieldset class="finding-controls" :disabled="disabled" @click.stop>
    <label>
      Entity type
      <select :value="finding.effective_entity_type" @change="setClassification">
        <option
          v-for="option in classificationOptions"
          :key="option.entity_type"
          :value="option.entity_type"
        >
          {{ option.display_name }}
        </option>
      </select>
    </label>
    <template v-if="isPlainTextTarget(finding.target)">
      <label>
        Line ID
        <input
          :value="finding.target.locator.line_id"
          @change="setDocumentTextTarget('line_id', $event)"
        />
      </label>
      <label>
        Exact text
        <textarea
          :value="finding.target.locator.exact_text"
          rows="3"
          @change="setDocumentTextTarget('exact_text', $event)"
        />
      </label>
    </template>
    <template v-else-if="isAudioTarget(finding.target)">
      <label>
        Start time
        <input
          class="audio-time-input"
          type="text"
          inputmode="numeric"
          :pattern="DURATION_TIMECODE_PATTERN"
          placeholder="00:00:00:000"
          :value="formatDurationSeconds(finding.target.range.start_time)"
          @input="clearTimeValidity"
          @change="setAudioTarget('start_time', $event)"
        />
      </label>
      <label>
        End time
        <input
          class="audio-time-input"
          type="text"
          inputmode="numeric"
          :pattern="DURATION_TIMECODE_PATTERN"
          placeholder="00:00:00:000"
          :value="formatDurationSeconds(finding.target.range.end_time)"
          @input="clearTimeValidity"
          @change="setAudioTarget('end_time', $event)"
        />
      </label>
    </template>
    <div class="effect-control-row">
      <label>
        Action
        <select :value="layer.action" @change="setAction($event)">
          <option v-for="action in actionsForLayer" :key="action" :value="action">
            {{ labelFor(action) }}
          </option>
        </select>
      </label>
      <button
        class="icon-button effect-visibility-button"
        type="button"
        :aria-pressed="layer.enabled"
        :aria-label="layer.enabled ? 'Hide effect on preview' : 'Show effect on preview'"
        @click="toggleVisibility"
      >
        <svg v-if="layer.enabled" aria-hidden="true" viewBox="0 0 24 24">
          <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
        <svg v-else aria-hidden="true" viewBox="0 0 24 24">
          <path d="M3 3l18 18" />
          <path d="M10.6 10.6A3 3 0 0 0 13.4 13.4" />
          <path d="M9.9 5.2A9 9 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-2.4 3.4" />
          <path d="M6.1 6.9C3.5 8.7 2 12 2 12s3.5 7 10 7a9 9 0 0 0 4.1-.9" />
        </svg>
      </button>
    </div>
    <label>
      Effect
      <select :value="selectedEffect" @change="setEffect($event)">
        <option v-for="effect in effectsForAction" :key="effect" :value="effect">
          {{ effectLabel(effect) }}
        </option>
      </select>
    </label>
    <label v-if="selectedEffect === 'token_replace'">
      Replacement
      <input :value="layer.custom_text || ''" @change="setReplacement" />
    </label>
    <label>
      Note
      <textarea
        :value="finding.reviewer_note || ''"
        rows="3"
        @change="setReviewerNote"
      />
    </label>
    <label>
      Decision
      <select :value="finding.review_decision" @change="setFinding('review_decision', $event)">
        <option v-for="decision in decisions" :key="decision" :value="decision">
          {{ labelFor(decision) }}
        </option>
      </select>
    </label>
  </fieldset>
</template>

<script setup lang="ts">
import { computed, watch } from "vue";
import type {
  Finding,
  FindingUpdateRequest,
  ClassificationOption,
  Layer,
  LayerAction,
  LayerEffect,
  LayerUpdateRequest,
  ReviewOptions,
} from "../api/contracts";
import {
  isAudioTarget,
  isPlainTextTarget,
} from "../api/contracts";
import {
  DURATION_TIMECODE_LABEL,
  DURATION_TIMECODE_PATTERN,
  formatDurationSeconds,
  parseDurationTimecode,
} from "../utils/duration";

const props = defineProps<{
  finding: Finding;
  layer: Layer;
  reviewOptions: ReviewOptions | null;
  classificationOptions: ClassificationOption[];
  disabled: boolean;
}>();
const emit = defineEmits<{
  "update-finding": [findingId: string, updates: FindingUpdateRequest];
  "update-layer": [layerId: string, updates: LayerUpdateRequest];
}>();

const decisions = computed(() => props.reviewOptions?.review_decisions ?? []);
const mediaRules = computed(
  () => props.reviewOptions?.supported_effects_by_kind_and_action[props.finding.target.kind] ?? {},
);
const actionsForLayer = computed(() =>
  Object.keys(mediaRules.value) as LayerAction[],
);
const effectsForAction = computed(() => mediaRules.value[props.layer.action] ?? []);
const selectedEffect = computed(() =>
  effectsForAction.value.includes(props.layer.effect)
    ? props.layer.effect
    : effectsForAction.value[0] || props.layer.effect,
);

watch(selectedEffect, (effect) => {
  if (!props.disabled && effect !== props.layer.effect) {
    emit("update-layer", props.layer.id, { effect });
  }
});

function setFinding(field: keyof Finding, event: Event) {
  emit("update-finding", props.finding.id, {
    [field]: (event.target as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement).value,
  } as FindingUpdateRequest);
}

function setClassification(event: Event) {
  const value = (event.target as HTMLSelectElement).value;
  emit("update-finding", props.finding.id, {
    reviewed_entity_type: value === props.finding.detected_entity_type ? null : value,
  });
}

function setAction(event: Event) {
  const action = (event.target as HTMLSelectElement).value as LayerAction;
  const effect = mediaRules.value[action]?.[0];
  if (!effect) return;
  emit("update-layer", props.layer.id, {
    action,
    effect,
    ...(effect === "token_replace" ? {} : { custom_text: null }),
  });
}

function setEffect(event: Event) {
  const effect = (event.target as HTMLSelectElement).value as LayerEffect;
  emit("update-layer", props.layer.id, {
    effect,
    ...(effect === "token_replace" ? {} : { custom_text: null }),
  });
}

function setReplacement(event: Event) {
  const value = (event.target as HTMLInputElement).value;
  emit("update-layer", props.layer.id, {
    custom_text: value.trim() ? value : null,
  });
}

function setReviewerNote(event: Event) {
  const value = (event.target as HTMLTextAreaElement).value;
  emit("update-finding", props.finding.id, {
    reviewer_note: value.trim() ? value : null,
  });
}

function setDocumentTextTarget(field: "line_id" | "exact_text", event: Event) {
  if (!isPlainTextTarget(props.finding.target)) {
    return;
  }
  const value = (event.target as HTMLInputElement | HTMLTextAreaElement).value;
  emit("update-finding", props.finding.id, {
    target: {
      ...props.finding.target,
      locator: { ...props.finding.target.locator, [field]: value },
    },
  });
}

function setAudioTarget(field: "start_time" | "end_time", event: Event) {
  if (!isAudioTarget(props.finding.target)) return;
  const input = event.target as HTMLInputElement;
  const seconds = parseDurationTimecode(input.value);
  if (seconds === null) {
    input.setCustomValidity(`Use ${DURATION_TIMECODE_LABEL}, for example 00:01:23:456.`);
    input.reportValidity();
    return;
  }
  input.setCustomValidity("");
  emit("update-finding", props.finding.id, {
    target: {
      ...props.finding.target,
      range: {
        ...props.finding.target.range,
        [field]: seconds,
      },
    },
  });
}

function clearTimeValidity(event: Event) {
  (event.target as HTMLInputElement).setCustomValidity("");
}

function toggleVisibility() {
  emit("update-layer", props.layer.id, { enabled: !props.layer.enabled });
}

function labelFor(value: string) {
  return value.replaceAll("_", " ");
}

function effectLabel(effect: LayerEffect) {
  return effect === "box" ? "redact" : labelFor(effect);
}
</script>
