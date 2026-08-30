import { defineStore } from "pinia";
import { api } from "../api/client";
import type {
  InstructionSetCreateRequest,
  InstructionSetDefinition,
  InstructionSetsResponse,
  InstructionSetSummary,
  InstructionSetUpdateRequest,
} from "../api/contracts";
import { errorMessage, useNotificationsStore } from "./notifications";

interface InstructionSetState {
  items: InstructionSetSummary[];
  activeInstructionSetId: string | null;
  loading: boolean;
}

export const useInstructionSetsStore = defineStore("instructionSets", {
  state: (): InstructionSetState => ({
    items: [],
    activeInstructionSetId: null,
    loading: false,
  }),
  actions: {
    async load(): Promise<boolean> {
      this.loading = true;
      try {
        const response: InstructionSetsResponse = await api.listInstructionSets();
        this.items = response.items;
        this.activeInstructionSetId = response.active_instruction_set_id;
        return true;
      } catch (error) {
        useNotificationsStore().error(errorMessage(error, "Policies could not be loaded."));
        return false;
      } finally {
        this.loading = false;
      }
    },
    async get(instructionSetId: string): Promise<InstructionSetDefinition | null> {
      this.loading = true;
      try {
        return await api.getInstructionSet(instructionSetId);
      } catch (error) {
        useNotificationsStore().error(errorMessage(error, "The policy could not be loaded."));
        return null;
      } finally {
        this.loading = false;
      }
    },
    async create(request: InstructionSetCreateRequest): Promise<string | null> {
      this.loading = true;
      try {
        const id = await api.createInstructionSet(request);
        await api.activateInstructionSet(id);
        await this.load();
        return id;
      } catch (error) {
        useNotificationsStore().error(errorMessage(error, "The policy could not be created."));
        return null;
      } finally {
        this.loading = false;
      }
    },
    async update(instructionSetId: string, request: InstructionSetUpdateRequest): Promise<boolean> {
      this.loading = true;
      try {
        await api.updateInstructionSet(instructionSetId, request);
        await api.activateInstructionSet(instructionSetId);
        await this.load();
        return true;
      } catch (error) {
        useNotificationsStore().error(errorMessage(error, "The policy could not be updated."));
        return false;
      } finally {
        this.loading = false;
      }
    },
    async activate(instructionSetId: string): Promise<boolean> {
      try {
        await api.activateInstructionSet(instructionSetId);
        this.activeInstructionSetId = instructionSetId;
        return true;
      } catch (error) {
        useNotificationsStore().error(errorMessage(error, "The policy could not be selected."));
        return false;
      }
    },
    async remove(instructionSetId: string): Promise<boolean> {
      this.loading = true;
      try {
        await api.deleteInstructionSet(instructionSetId);
        await this.load();
        return true;
      } catch (error) {
        useNotificationsStore().error(errorMessage(error, "The policy could not be deleted."));
        return false;
      } finally {
        this.loading = false;
      }
    },
  },
});
