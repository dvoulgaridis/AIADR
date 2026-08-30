import { defineStore } from "pinia";
import { api } from "../api/client";
import type {
  ApiFormat,
  DependencyStatus,
  Model,
  ModelWriteRequest,
  ProviderWriteSettings,
} from "../api/contracts";
import { errorMessage, useNotificationsStore } from "./notifications";

type ProviderDraft = ProviderWriteSettings & { api_key_configured: boolean };

function newModelId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(6));
  const suffix = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `model_${suffix}`;
}

export interface ModelDraft {
  model_id: string;
  label: string;
  provider: ProviderDraft;
  capabilities: Model["capabilities"];
  configured: boolean;
}

export function emptyProvider(apiFormat: ApiFormat): ProviderDraft {
  const common = {
    api_key: "",
    api_key_configured: false,
    model: "",
    max_output_tokens: null,
    temperature: null,
    timeout: 120,
    max_retries: 1,
  };
  switch (apiFormat) {
    case "openai_compatible":
      return {
        ...common,
        api_format: apiFormat,
        base_url: "",
        context_window_tokens: null,
        output_token_parameter: "max_tokens",
      };
    case "anthropic_messages":
      return { ...common, api_format: apiFormat };
    case "google_genai":
      return { ...common, api_format: apiFormat };
  }
}

export const emptyModel = (): ModelDraft => ({
  model_id: newModelId(),
  label: "",
  provider: emptyProvider("openai_compatible"),
  capabilities: {
    supports_vision: false,
    supports_audio: false,
    supports_json_mode: false,
  },
  configured: false,
});

export function editableModel(model: Model): ModelDraft {
  return {
    model_id: model.model_id,
    label: model.label,
    provider: {
      ...model.provider,
      api_key: null,
    } as ProviderDraft,
    capabilities: { ...model.capabilities },
    configured: model.configured,
  };
}

function providerWriteSettings(provider: ProviderDraft): ProviderWriteSettings {
  const { api_key_configured: _, ...settings } = provider;
  return settings;
}

function modelWriteRequest(model: ModelDraft): ModelWriteRequest {
  return {
    label: model.label,
    provider: providerWriteSettings(model.provider),
    capabilities: { ...model.capabilities },
  };
}

export const useModelsStore = defineStore("models", {
  state: () => ({
    models: [] as Model[],
    activeModelId: null as string | null,
    ffmpeg: null as DependencyStatus | null,
    libreoffice: null as DependencyStatus | null,
    dependenciesRequestGeneration: 0,
    loading: false,
  }),
  actions: {
    async loadModels() {
      this.loading = true;
      try {
        const response = await api.listModels();
        this.models = response.models;
        this.activeModelId = response.active_model_id;
        return true;
      } catch (error) {
        useNotificationsStore().error(errorMessage(error, "Failed to load models."));
        return false;
      } finally {
        this.loading = false;
      }
    },
    async loadDependencies() {
      const generation = ++this.dependenciesRequestGeneration;
      try {
        const response = await api.getDependencies();
        if (generation !== this.dependenciesRequestGeneration) return;
        this.ffmpeg = response.ffmpeg;
        this.libreoffice = response.libreoffice;
      } catch (error) {
        if (generation !== this.dependenciesRequestGeneration) return;
        useNotificationsStore().error(errorMessage(error, "Failed to check dependencies."));
      }
    },
    async save(model: ModelDraft) {
      this.loading = true;
      try {
        await api.putModel(model.model_id, modelWriteRequest(model));
        await api.activateModel(model.model_id);
        const loaded = await this.loadModels();
        return loaded
          ? (this.models.find((item) => item.model_id === model.model_id) ?? null)
          : null;
      } catch (error) {
        useNotificationsStore().error(errorMessage(error, "Failed to save model."));
        return null;
      } finally {
        this.loading = false;
      }
    },
    async activate(modelId: string) {
      try {
        await api.activateModel(modelId);
        this.activeModelId = modelId;
        return true;
      } catch (error) {
        useNotificationsStore().error(errorMessage(error, "Failed to select model."));
        return false;
      }
    },
    async remove(modelId: string) {
      this.loading = true;
      try {
        await api.deleteModel(modelId);
        return await this.loadModels();
      } catch (error) {
        useNotificationsStore().error(errorMessage(error, "Failed to delete model."));
        return false;
      } finally {
        this.loading = false;
      }
    },
  },
});
