<template>
  <section class="settings-grid" :class="{ 'settings-grid-unified': unified }">
    <div class="panel model-list-panel" :class="{ 'embedded-panel': unified }">
      <div class="section-head">
        <h2>Models</h2>
        <button
          type="button"
          class="header-add-button"
          aria-label="New model"
          @click="newModel"
        >
          <span aria-hidden="true">+</span>
        </button>
      </div>
      <p v-if="!store.models.length" class="muted">No saved models yet.</p>
      <button
        v-for="model in store.models"
        :key="model.model_id"
        type="button"
        class="model-list-item"
        :class="{ active: model.model_id === selectedModelId }"
        :ref="(element) => setModelButtonRef(model.model_id, element)"
        @click="void editModel(model.model_id)"
      >
        <span>
          <strong>{{ model.label || model.provider.model }}</strong>
          <small>{{ model.provider.model || "No model name" }}</small>
        </span>
        <small>{{ formatLabel(model.provider.api_format) }}</small>
      </button>
    </div>

    <form
      class="panel grid-form model-editor"
      :class="{ 'embedded-panel': unified }"
      @submit.prevent="save"
    >
      <label>
        Label
        <input v-model="draft.label" required />
      </label>
      <label>
        API format
        <select :value="selectedApiFormat" @change="setApiFormat">
          <option value="">Select</option>
          <option value="openai_compatible">OpenAI-compatible Chat Completions</option>
          <option value="anthropic_messages">Anthropic Messages</option>
          <option value="google_genai">Google Gen AI</option>
        </select>
      </label>
      <template v-if="selectedApiFormat">
        <div class="form-divider"></div>
      <label v-if="draft.provider.api_format === 'openai_compatible'">
        Base URL
        <input v-model="draft.provider.base_url" placeholder="http://localhost:11434/v1" />
      </label>
      <label>
        API key{{ selectedApiFormat === "openai_compatible" ? " (optional)" : "" }}
        <input
          :value="draft.provider.api_key ?? ''"
          type="password"
          autocomplete="off"
          :placeholder="
            draft.provider.api_key === null && draft.provider.api_key_configured
              ? 'Key is configured'
              : ''
          "
          @input="setApiKey"
        />
      </label>
      <label>
        Model
        <input v-model="draft.provider.model" placeholder="Model identifier" />
      </label>
      <label>
        Max output tokens{{
          draft.provider.api_format === "anthropic_messages" ? "" : " (optional)"
        }}
        <input
          :value="draft.provider.max_output_tokens ?? ''"
          inputmode="numeric"
          min="128"
          step="128"
          type="number"
          @input="setOptionalProviderInteger('max_output_tokens', $event)"
          @keydown="preventIntegerKey"
        />
      </label>
      <template v-if="draft.provider.api_format === 'openai_compatible'">
        <label>
          Context window
          <input
            :value="draft.provider.context_window_tokens ?? ''"
            inputmode="numeric"
            min="1"
            step="1"
            type="number"
            @input="setOptionalProviderInteger('context_window_tokens', $event)"
            @keydown="preventIntegerKey"
          />
        </label>
        <label>
          Output token parameter
          <select v-model="draft.provider.output_token_parameter">
            <option value="max_tokens">max_tokens</option>
            <option value="max_completion_tokens">max_completion_tokens</option>
          </select>
        </label>
      </template>
      <label>
        Temperature (optional)
        <input
          :value="draft.provider.temperature ?? ''"
          inputmode="decimal"
          min="0"
          :max="temperatureMaximum"
          step="0.1"
          type="number"
          @input="setOptionalProviderNumber('temperature', $event)"
          @keydown="preventDecimalKey"
        />
      </label>
      <label>
        Timeout (seconds)
        <input
          :value="draft.provider.timeout"
          inputmode="decimal"
          min="1"
          step="1"
          type="number"
          @input="setProviderNumber('timeout', $event)"
          @keydown="preventDecimalKey"
        />
      </label>
      <label>
        Max retries
        <input
          :value="draft.provider.max_retries"
          inputmode="numeric"
          min="0"
          max="5"
          step="1"
          type="number"
          @input="setProviderInteger('max_retries', $event)"
          @keydown="preventIntegerKey"
        />
      </label>
      <label class="check-row">
        <input
          v-model="draft.capabilities.supports_json_mode"
          type="checkbox"
          :disabled="draft.provider.api_format === 'anthropic_messages'"
        />
        JSON mode
        <span class="help-tip" tabindex="0" data-tooltip="Enforces JSON responses.">?</span>
      </label>
      <label class="check-row">
        <input v-model="draft.capabilities.supports_vision" type="checkbox" />
        Vision
      </label>
      <label class="check-row">
        <input
          v-model="draft.capabilities.supports_audio"
          type="checkbox"
          :disabled="draft.provider.api_format === 'anthropic_messages'"
        />
        Audio input
        <span class="help-tip" tabindex="0" data-tooltip="Supports audio attachments.">?</span>
      </label>
      <section class="model-metadata-section">
        <h3>Model metadata</h3>
        <textarea
          :value="formattedModelMetadata"
          aria-label="Model metadata JSON"
          readonly
          rows="10"
          spellcheck="false"
        ></textarea>
      </section>
      <div class="button-row form-actions">
        <button type="submit" :disabled="store.loading">Save</button>
        <button
          type="button"
          :disabled="store.loading || !selectedModelId"
          @click="remove"
        >
          Delete
        </button>
      </div>
      </template>
    </form>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from "vue";
import { api } from "../api/client";
import type { ApiFormat, ModelMetadata, Model } from "../api/contracts";
import {
  editableModel,
  emptyModel,
  emptyProvider,
  type ModelDraft,
  useModelsStore,
} from "../stores/models";
import { errorMessage, useNotificationsStore } from "../stores/notifications";

defineProps<{ unified?: boolean }>();
const store = useModelsStore();
const notifications = useNotificationsStore();
const selectedModelId = ref("");
const selectedApiFormat = ref<ApiFormat | "">("");
const draft = reactive<ModelDraft>(emptyModel());
const modelMetadata = ref<ModelMetadata | null>(null);
let metadataRequestSequence = 0;
const modelButtonRefs = new Map<string, HTMLButtonElement>();
const navigationKeys = new Set([
  "Backspace",
  "Delete",
  "Tab",
  "Enter",
  "Escape",
  "ArrowLeft",
  "ArrowRight",
  "ArrowUp",
  "ArrowDown",
  "Home",
  "End",
]);
const temperatureMaximum = computed(() => {
  if (draft.provider.api_format === "openai_compatible") return 2;
  if (draft.provider.api_format === "anthropic_messages") return 1;
  return undefined;
});
const formattedModelMetadata = computed(() =>
  modelMetadata.value ? JSON.stringify(modelMetadata.value, null, 2) : "N/A",
);

onMounted(async () => {
  await store.loadModels();
  if (store.activeModelId) await editModel(store.activeModelId, false);
});

function assignDraft(model: Model) {
  Object.assign(draft, editableModel(model));
}

async function editModel(modelId: string, activate = true) {
  const model = store.models.find((item) => item.model_id === modelId);
  if (!model) return;
  if (activate && !(await store.activate(modelId))) return;
  selectedModelId.value = modelId;
  selectedApiFormat.value = model.provider.api_format;
  assignDraft(model);
  void loadModelMetadata(model);
}

function newModel() {
  selectedModelId.value = "";
  selectedApiFormat.value = "";
  metadataRequestSequence += 1;
  modelMetadata.value = null;
  Object.assign(draft, emptyModel());
}

async function save() {
  if (!selectedApiFormat.value) return;
  const saved = await store.save(draft);
  if (!saved) return;
  selectedModelId.value = saved.model_id;
  selectedApiFormat.value = saved.provider.api_format;
  assignDraft(saved);
  void loadModelMetadata(saved);
}

function setApiFormat(event: Event) {
  const value = (event.target as HTMLSelectElement).value;
  metadataRequestSequence += 1;
  modelMetadata.value = null;
  selectedApiFormat.value = value as ApiFormat | "";
  if (!value) return;
  const apiFormat = value as ApiFormat;
  draft.provider = emptyProvider(apiFormat);
  if (apiFormat === "anthropic_messages") {
    draft.capabilities.supports_audio = false;
    draft.capabilities.supports_json_mode = false;
  }
}

function setApiKey(event: Event) {
  draft.provider.api_key = (event.target as HTMLInputElement).value;
}

function inputNumber(event: Event): number | null {
  const value = (event.target as HTMLInputElement).value;
  return value === "" ? null : Number(value);
}

function setOptionalProviderInteger(field: string, event: Event) {
  const value = inputNumber(event);
  (draft.provider as unknown as Record<string, number | null>)[field] =
    value === null ? null : Math.trunc(value);
}

function setProviderInteger(field: string, event: Event) {
  const value = inputNumber(event);
  (draft.provider as unknown as Record<string, number>)[field] = Math.trunc(value ?? 0);
}

function setProviderNumber(field: string, event: Event) {
  (draft.provider as unknown as Record<string, number>)[field] = inputNumber(event) ?? 0;
}

function setOptionalProviderNumber(field: string, event: Event) {
  (draft.provider as unknown as Record<string, number | null>)[field] = inputNumber(event);
}

function canInspectModel(model: Model): boolean {
  if (!model.provider.model) return false;
  if (model.provider.api_format === "openai_compatible") {
    return Boolean(model.provider.base_url);
  }
  return model.provider.api_key_configured;
}

async function loadModelMetadata(model: Model) {
  const requestSequence = ++metadataRequestSequence;
  modelMetadata.value = null;
  if (!canInspectModel(model)) return;
  try {
    const metadata = await api.getModelModelMetadata(model.model_id);
    if (
      requestSequence === metadataRequestSequence &&
      selectedModelId.value === model.model_id
    ) {
      modelMetadata.value = metadata;
    }
  } catch (error) {
    if (requestSequence !== metadataRequestSequence) return;
    notifications.error(errorMessage(error, "Failed to load model metadata."));
  }
}

async function remove() {
  const deletedIndex = store.models.findIndex(
    (model) => model.model_id === draft.model_id,
  );
  const adjacentId =
    deletedIndex > 0
      ? store.models[deletedIndex - 1]?.model_id
      : store.models[deletedIndex + 1]?.model_id;
  const removed = await store.remove(draft.model_id);
  if (!removed) return;
  const nextId =
    adjacentId && store.models.some((model) => model.model_id === adjacentId)
      ? adjacentId
      : store.models[0]?.model_id || "";
  if (nextId) {
    await editModel(nextId);
  } else {
    selectedModelId.value = "";
    selectedApiFormat.value = "";
    metadataRequestSequence += 1;
    modelMetadata.value = null;
    Object.assign(draft, emptyModel());
  }
  await nextTick();
  modelButtonRefs.get(nextId)?.focus();
}

function setModelButtonRef(modelId: string, element: unknown) {
  if (element instanceof HTMLButtonElement) {
    modelButtonRefs.set(modelId, element);
    return;
  }
  modelButtonRefs.delete(modelId);
}

function preventIntegerKey(event: KeyboardEvent) {
  if (event.ctrlKey || event.metaKey || navigationKeys.has(event.key)) return;
  if (!/^\d$/.test(event.key)) event.preventDefault();
}

function preventDecimalKey(event: KeyboardEvent) {
  if (event.ctrlKey || event.metaKey || navigationKeys.has(event.key)) return;
  const input = event.currentTarget as HTMLInputElement;
  if (event.key === "." && !input.value.includes(".")) return;
  if (!/^\d$/.test(event.key)) event.preventDefault();
}

function formatLabel(value: string): string {
  return value.replaceAll("_", " ");
}
</script>
