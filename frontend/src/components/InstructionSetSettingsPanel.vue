<template>
  <section class="settings-grid settings-grid-unified">
    <div class="panel model-list-panel embedded-panel">
      <div class="section-head">
        <h2>Policies</h2>
        <button
          type="button"
          class="header-add-button"
          aria-label="New policy"
          @click="newPolicy"
        >
          <span aria-hidden="true">+</span>
        </button>
      </div>
      <p v-if="!store.items.length" class="muted">No policies available.</p>
      <button
        v-for="item in store.items"
        :key="item.id"
        type="button"
        class="model-list-item"
        :class="{ active: item.id === selectedId }"
        @click="void editPolicy(item.id)"
      >
        <span>
          <strong>{{ item.name }}</strong>
          <small>{{ item.id }}</small>
        </span>
      </button>
    </div>

    <form class="panel grid-form instruction-set-editor embedded-panel" @submit.prevent="save">
      <label>
        ID
        <input v-model="draft.id" :readonly="Boolean(selectedId)" required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" />
      </label>
      <label>
        Name
        <input v-model="draft.name" required />
      </label>
      <label class="form-wide">
        Policy JSON
        <textarea v-model="draft.policy" required rows="16" spellcheck="false" />
      </label>
      <label class="form-wide">
        Text prompt
        <textarea v-model="draft.prompts.text" required rows="8" />
      </label>
      <label class="form-wide">
        Document prompt
        <textarea v-model="draft.prompts.document" required rows="8" />
      </label>
      <label class="form-wide">
        Image prompt
        <textarea v-model="draft.prompts.image" required rows="8" />
      </label>
      <label class="form-wide">
        Audio prompt
        <textarea v-model="draft.prompts.audio" required rows="8" />
      </label>
      <div class="button-row form-actions">
        <button type="submit" :disabled="store.loading">Save</button>
        <button type="button" :disabled="store.loading || !selectedId" @click="remove">Delete</button>
      </div>
    </form>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import type { InstructionSetPrompts } from "../api/contracts";
import { useInstructionSetsStore } from "../stores/instructionSets";
import { useNotificationsStore } from "../stores/notifications";

interface InstructionSetDraft {
  id: string;
  name: string;
  contentHash: string;
  policy: string;
  prompts: InstructionSetPrompts;
}

const EMPTY_POLICY = {
  defaults: {
    privacy_category: "unknown",
    special_category_type: "none",
    privacy_risk: "medium",
    effects: {
      document: { action: "redact", effect: "box" },
      image: { action: "redact", effect: "box" },
      audio: { action: "redact", effect: "bleep" },
    },
  },
  entity_rules: {
    not_personal_data: {
      display_name: "Not personal data",
      privacy_category: "not_personal_data",
      privacy_risk: "low",
      effects: {
        document: { action: "preserve", effect: "none" },
        image: { action: "preserve", effect: "none" },
        audio: { action: "preserve", effect: "none" },
      },
    },
  },
};

function emptyDraft(): InstructionSetDraft {
  return {
    id: "",
    name: "",
    contentHash: "",
    policy: JSON.stringify(EMPTY_POLICY, null, 2),
    prompts: { text: "", document: "", image: "", audio: "" },
  };
}

const store = useInstructionSetsStore();
const notifications = useNotificationsStore();
const selectedId = ref("");
const draft = reactive<InstructionSetDraft>(emptyDraft());

function assignDraft(value: InstructionSetDraft) {
  Object.assign(draft, value);
}

function newPolicy() {
  selectedId.value = "";
  assignDraft(emptyDraft());
}

async function editPolicy(instructionSetId: string, activate = true) {
  if (activate && !(await store.activate(instructionSetId))) return;
  const definition = await store.get(instructionSetId);
  if (!definition) return;
  selectedId.value = definition.id;
  assignDraft({
    id: definition.id,
    name: definition.name,
    contentHash: definition.content_hash,
    policy: JSON.stringify(definition.policy, null, 2),
    prompts: { ...definition.prompts },
  });
}

function parsePolicy(): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(draft.policy);
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error();
    return value as Record<string, unknown>;
  } catch {
    notifications.error("Policy JSON must contain one valid JSON object.");
    return null;
  }
}

async function save() {
  const policy = parsePolicy();
  if (!policy) return;
  const prompts = { ...draft.prompts };
  if (selectedId.value) {
    const saved = await store.update(selectedId.value, {
      name: draft.name.trim(),
      expected_content_hash: draft.contentHash,
      policy,
      prompts,
    });
    if (saved) await editPolicy(selectedId.value);
    return;
  }
  const id = await store.create({
    id: draft.id.trim(),
    name: draft.name.trim(),
    policy,
    prompts,
  });
  if (id) await editPolicy(id);
}

async function remove() {
  if (!selectedId.value) return;
  const index = store.items.findIndex((item) => item.id === selectedId.value);
  const adjacentId = index > 0 ? store.items[index - 1]?.id : store.items[index + 1]?.id;
  if (!(await store.remove(selectedId.value))) return;
  if (adjacentId && store.items.some((item) => item.id === adjacentId)) {
    await editPolicy(adjacentId);
  } else {
    newPolicy();
  }
}

onMounted(async () => {
  await store.load();
  if (store.activeInstructionSetId) {
    await editPolicy(store.activeInstructionSetId, false);
  }
});
</script>
