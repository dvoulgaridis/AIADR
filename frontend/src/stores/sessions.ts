import { defineStore } from "pinia";
import { api } from "../api/client";
import type {
  AuditEvent,
  ClassificationOption,
  ExportCreateResponse,
  FindingTarget,
  FindingUpdateRequest,
  Layer,
  LayerUpdateRequest,
  ManualFindingCreateRequest,
  ModelInteractionLog,
  ReviewOptions,
  Session,
} from "../api/contracts";
import { isAbortError } from "../api/errors";
import { errorMessage, useNotificationsStore } from "./notifications";

export interface ActiveSessionProjection {
  session: Session;
  layers: Layer[];
  modelLogs: ModelInteractionLog[];
  auditEvents: AuditEvent[];
  lastEventHash: string | null;
  reviewOptions: ReviewOptions;
  classificationOptions: ClassificationOption[];
}

export interface SessionInteractionState {
  selectedLayerId: string | null;
  creatingFinding: boolean;
  newFindingTarget: FindingTarget | null;
}

interface SessionsState {
  sessions: Session[];
  activeProjection: ActiveSessionProjection | null;
  interaction: SessionInteractionState;
  isSessionsLoading: boolean;
  isActiveSessionLoading: boolean;
  pendingCommandSessionIds: string[];
  loadSequence: number;
}

function initialInteraction(): SessionInteractionState {
  return {
    selectedLayerId: null,
    creatingFinding: false,
    newFindingTarget: null,
  };
}

export const useSessionsStore = defineStore("sessions", {
  state: (): SessionsState => ({
    sessions: [],
    activeProjection: null,
    interaction: initialInteraction(),
    isSessionsLoading: false,
    isActiveSessionLoading: false,
    pendingCommandSessionIds: [],
    loadSequence: 0,
  }),
  getters: {
    activeSession(state): Session | null {
      return state.activeProjection?.session ?? null;
    },
    activeSessionId(state): string | null {
      return state.activeProjection?.session.session_id ?? null;
    },
    selectedLayer(state): Layer | null {
      return (
        state.activeProjection?.layers.find(
          (layer) => layer.id === state.interaction.selectedLayerId,
        ) ?? null
      );
    },
    isAnalysisActive(state): boolean {
      return state.activeProjection?.session.analysis_active === true;
    },
    isCommandPending(state): boolean {
      const sessionId = state.activeProjection?.session.session_id;
      return Boolean(
        sessionId && state.pendingCommandSessionIds.includes(sessionId),
      );
    },
    isActiveSessionBusy(): boolean {
      return this.isAnalysisActive || this.isCommandPending;
    },
    canAnalyze(): boolean {
      return this.activeSession !== null && !this.isActiveSessionBusy;
    },
    canExport(): boolean {
      return this.activeSession !== null && !this.isActiveSessionBusy;
    },
    canRename(): boolean {
      return this.activeSession !== null && !this.isActiveSessionBusy;
    },
    canPurge(): boolean {
      return this.activeSession !== null && !this.isActiveSessionBusy;
    },
    canAddFinding(state): boolean {
      return Boolean(
        state.activeProjection?.classificationOptions.length &&
          !this.isActiveSessionBusy,
      );
    },
    canEditReview(): boolean {
      return this.activeSession !== null && !this.isActiveSessionBusy;
    },
  },
  actions: {
    async loadSessions(): Promise<void> {
      this.isSessionsLoading = true;
      try {
        this.sessions = await api.listSessions();
      } catch (error) {
        useNotificationsStore().error(
          errorMessage(error, "Failed to load reviews."),
        );
      } finally {
        this.isSessionsLoading = false;
      }
    },
    upsertSession(session: Session): void {
      const index = this.sessions.findIndex(
        (item) => item.session_id === session.session_id,
      );
      if (index >= 0) {
        this.sessions[index] = session;
      } else {
        this.sessions.unshift(session);
      }
    },
    removeSession(sessionId: string): void {
      this.sessions = this.sessions.filter(
        (session) => session.session_id !== sessionId,
      );
    },
    async loadActiveSession(
      sessionId: string,
      signal?: AbortSignal,
    ): Promise<Session | null> {
      const sequence = ++this.loadSequence;
      const previous = this.activeProjection;
      const switching = previous?.session.session_id !== sessionId;
      const selectedLayerId = switching
        ? null
        : this.interaction.selectedLayerId;

      if (switching) {
        this.activeProjection = null;
        this.interaction = initialInteraction();
      }
      this.isActiveSessionLoading = true;

      try {
        const [session, layers, modelLogs, auditEvents, reviewOptions] =
          await Promise.all([
            api.getSession(sessionId, signal),
            api.getLayers(sessionId, signal),
            api.getModelLogs(sessionId, signal),
            api.getAuditEvents(sessionId, signal),
            api.getReviewOptions(signal),
          ]);

        let classificationOptions: ClassificationOption[] = [];
        if (session.instruction_set) {
          try {
            classificationOptions = (
              await api.getClassificationOptions(sessionId, signal)
            ).options;
          } catch (error) {
            if (isAbortError(error)) throw error;
            if (sequence === this.loadSequence) {
              useNotificationsStore().error(
                errorMessage(
                  error,
                  "Classification options could not be loaded.",
                ),
              );
            }
          }
        }

        if (signal?.aborted || sequence !== this.loadSequence) return null;

        const candidate: ActiveSessionProjection = {
          session,
          layers: layers.layers,
          modelLogs: modelLogs.logs,
          auditEvents: auditEvents.events,
          lastEventHash: auditEvents.last_event_hash,
          reviewOptions,
          classificationOptions,
        };
        this.activeProjection = candidate;
        this.interaction.selectedLayerId =
          selectedLayerId &&
          candidate.layers.some((layer) => layer.id === selectedLayerId)
            ? selectedLayerId
            : null;
        this.upsertSession(session);
        if (session.public_error) {
          useNotificationsStore().error(session.public_error);
        }
        return session;
      } catch (error) {
        if (!isAbortError(error) && sequence === this.loadSequence) {
          useNotificationsStore().error(
            errorMessage(error, "Failed to load session."),
          );
        }
        return null;
      } finally {
        if (sequence === this.loadSequence) {
          this.isActiveSessionLoading = false;
        }
      }
    },
    async refreshActiveSession(sessionId: string): Promise<Session | null> {
      if (this.activeProjection?.session.session_id !== sessionId) return null;
      return this.loadActiveSession(sessionId);
    },
    clearActiveSession(): void {
      this.loadSequence += 1;
      this.activeProjection = null;
      this.interaction = initialInteraction();
      this.isActiveSessionLoading = false;
    },
    async withPendingCommand<T>(
      sessionId: string,
      command: () => Promise<T>,
    ): Promise<T | undefined> {
      if (this.pendingCommandSessionIds.includes(sessionId)) return undefined;
      this.pendingCommandSessionIds = [
        ...this.pendingCommandSessionIds,
        sessionId,
      ];
      try {
        return await command();
      } finally {
        this.pendingCommandSessionIds = this.pendingCommandSessionIds.filter(
          (pendingId) => pendingId !== sessionId,
        );
      }
    },
    async upload(file: File): Promise<string | null> {
      try {
        return await api.uploadFile(file);
      } catch (error) {
        useNotificationsStore().error(errorMessage(error, "Upload failed."));
        return null;
      }
    },
    async requestAnalysis(): Promise<boolean> {
      if (!this.canAnalyze) return false;
      const sessionId = this.activeSessionId;
      if (!sessionId) return false;
      const result = await this.withPendingCommand(sessionId, async () => {
        try {
          await api.requestAnalysis(sessionId);
          await this.refreshActiveSession(sessionId);
          return true;
        } catch (error) {
          useNotificationsStore().error(
            errorMessage(error, "Analysis could not be started."),
          );
          return false;
        }
      });
      return result ?? false;
    },
    async renameActiveSession(name: string): Promise<boolean> {
      if (!this.canRename) return false;
      const sessionId = this.activeSessionId;
      if (!sessionId) return false;
      const result = await this.withPendingCommand(sessionId, async () => {
        try {
          await api.updateSession(sessionId, { display_name: name });
          await this.loadSessions();
          await this.refreshActiveSession(sessionId);
          return true;
        } catch (error) {
          useNotificationsStore().error(
            errorMessage(error, "The review could not be renamed."),
          );
          return false;
        }
      });
      return result ?? false;
    },
    async purgeActiveSession(): Promise<string | null> {
      if (!this.canPurge) return null;
      const sessionId = this.activeSessionId;
      if (!sessionId) return null;
      const index = this.sessions.findIndex(
        (session) => session.session_id === sessionId,
      );
      const adjacentId =
        index > 0
          ? this.sessions[index - 1]?.session_id
          : this.sessions[index + 1]?.session_id;

      const result = await this.withPendingCommand(sessionId, async () => {
        try {
          await api.deleteSession(sessionId);
          this.removeSession(sessionId);
          if (this.activeSessionId === sessionId) this.clearActiveSession();
          return (
            (adjacentId &&
            this.sessions.some((session) => session.session_id === adjacentId)
              ? adjacentId
              : this.sessions[0]?.session_id) ?? null
          );
        } catch (error) {
          useNotificationsStore().error(
            errorMessage(error, "The review could not be deleted."),
          );
          return null;
        }
      });
      return result ?? null;
    },
    async createExport(): Promise<ExportCreateResponse | null> {
      if (!this.canExport) return null;
      const sessionId = this.activeSessionId;
      if (!sessionId) return null;
      const result = await this.withPendingCommand(sessionId, async () => {
        try {
          const created = await api.createExport(sessionId);
          await this.refreshActiveSession(sessionId);
          return created;
        } catch (error) {
          useNotificationsStore().error(
            errorMessage(error, "The export could not be created."),
          );
          return null;
        }
      });
      return result ?? null;
    },
    async addFinding(
      request: ManualFindingCreateRequest,
    ): Promise<string | null> {
      if (!this.canAddFinding) return null;
      const sessionId = this.activeSessionId;
      if (!sessionId) return null;
      const result = await this.withPendingCommand(sessionId, async () => {
        try {
          const layerId = await api.addFinding(sessionId, request);
          await this.refreshActiveSession(sessionId);
          if (
            this.activeSessionId === sessionId &&
            this.activeProjection?.layers.some((layer) => layer.id === layerId)
          ) {
            this.interaction.selectedLayerId = layerId;
          }
          return layerId;
        } catch (error) {
          useNotificationsStore().error(
            errorMessage(error, "The finding could not be added."),
          );
          return null;
        }
      });
      return result ?? null;
    },
    async updateFinding(
      findingId: string,
      updates: FindingUpdateRequest,
    ): Promise<void> {
      if (!this.canEditReview) return;
      const sessionId = this.activeSessionId;
      if (!sessionId) return;
      await this.withPendingCommand(sessionId, async () => {
        try {
          await api.updateFinding(sessionId, findingId, updates);
          await this.refreshActiveSession(sessionId);
        } catch (error) {
          useNotificationsStore().error(
            errorMessage(error, "The finding could not be updated."),
          );
        }
      });
    },
    async updateLayer(
      layerId: string,
      updates: LayerUpdateRequest,
    ): Promise<void> {
      if (!this.canEditReview) return;
      const sessionId = this.activeSessionId;
      if (!sessionId) return;
      await this.withPendingCommand(sessionId, async () => {
        try {
          await api.updateLayer(sessionId, layerId, updates);
          await this.refreshActiveSession(sessionId);
        } catch (error) {
          useNotificationsStore().error(
            errorMessage(error, "The finding effect could not be updated."),
          );
        }
      });
    },
    async resetEffectOverride(layerId: string): Promise<void> {
      if (!this.canEditReview) return;
      const sessionId = this.activeSessionId;
      if (!sessionId) return;
      await this.withPendingCommand(sessionId, async () => {
        try {
          await api.resetEffectOverride(sessionId, layerId);
          await this.refreshActiveSession(sessionId);
        } catch (error) {
          useNotificationsStore().error(
            errorMessage(error, "The finding effect could not be reset."),
          );
        }
      });
    },
    selectLayer(layerId: string | null): void {
      this.interaction.selectedLayerId = layerId;
    },
    beginFindingTarget(): void {
      if (!this.canAddFinding) return;
      this.interaction.selectedLayerId = null;
      this.interaction.creatingFinding = true;
      this.interaction.newFindingTarget = null;
    },
    setFindingTarget(target: FindingTarget): void {
      this.interaction.newFindingTarget = target;
      this.interaction.creatingFinding = false;
    },
    cancelFindingTarget(): void {
      this.interaction.creatingFinding = false;
      this.interaction.newFindingTarget = null;
    },
  },
});
