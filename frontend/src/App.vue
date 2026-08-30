<template>
  <div
    class="app-shell"
    :class="{ 'target-selection-active': interaction.creatingFinding }"
  >
    <aside
      class="review-sidebar"
      :class="{ collapsed: reviewSidebar.collapsed.value }"
      :style="{ width: `${reviewSidebar.renderedWidthRem.value}rem` }"
    >
      <div class="sidebar-top">
        <button type="button" class="sidebar-title" @click.stop="goHome">
          AIADR
        </button>
        <button
          type="button"
          class="header-add-button new-review-button"
          aria-label="New review"
          @click.stop="newReview"
        >
          <span aria-hidden="true">+</span>
        </button>
      </div>

      <nav
        v-if="!reviewSidebar.collapsed.value"
        class="review-history"
        aria-label="Review history"
      >
        <p v-if="isSessionsLoading" class="muted">Loading reviews...</p>
        <p v-else-if="!sessionItems.length" class="muted">No reviews yet.</p>
        <RouterLink
          v-for="session in sessionItems"
          :key="session.session_id"
          class="review-entry"
          :class="{ active: session.session_id === routeSessionId }"
          :to="reviewLocation(session.session_id)"
          @click.stop
        >
          <span>{{ reviewTitle(session) }}</span>
          <small>{{ session.source.kind }} · {{ session.status }}</small>
        </RouterLink>
      </nav>

      <div class="sidebar-bottom">
        <button
          type="button"
          class="icon-button settings-button"
          aria-label="Settings"
          @click.stop="openSettings()"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5Z" />
            <path
              d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 0 1-4 0v-.09A1.7 1.7 0 0 0 9 19.35a1.7 1.7 0 0 0-1.88.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.63 15 1.7 1.7 0 0 0 3.07 14H3a2 2 0 0 1 0-4h.09A1.7 1.7 0 0 0 4.65 9a1.7 1.7 0 0 0-.34-1.88l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.63 1.7 1.7 0 0 0 10 3.07V3a2 2 0 0 1 4 0v.09A1.7 1.7 0 0 0 15 4.65a1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.37 9c.23.63.82 1 1.5 1H21a2 2 0 0 1 0 4h-.09A1.7 1.7 0 0 0 19.4 15Z"
            />
          </svg>
        </button>
        <button
          type="button"
          class="app-theme-button theme-toggle"
          :aria-label="
            theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'
          "
          @click.stop="toggleTheme"
        >
          <svg
            class="theme-icon"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            preserveAspectRatio="xMidYMid meet"
            style="
              shape-rendering: geometricPrecision;
              text-rendering: geometricPrecision;
              image-rendering: optimizeQuality;
            "
            aria-hidden="true"
          >
            <defs>
              <clipPath id="theme-half-left">
                <rect x="0" y="0" width="12" height="24" />
              </clipPath>
            </defs>
            <circle
              cx="12"
              cy="12"
              r="10.25"
              fill="none"
              stroke="currentColor"
            />
            <circle
              cx="12"
              cy="12"
              r="10.25"
              fill="currentColor"
              clip-path="url(#theme-half-left)"
            />
          </svg>
        </button>
      </div>
      <button
        type="button"
        class="sidebar-resize-handle"
        aria-label="Resize review sidebar"
        @pointerdown.stop="reviewSidebar.startResize"
      />
    </aside>

    <main class="app-workspace" :class="{ 'has-findings': showFindingsSidebar }">
      <header v-if="showReviewActions" class="workspace-header">
        <form v-if="renaming" class="rename-form" @submit.prevent="saveRename">
          <input
            ref="renameInput"
            v-model="renameDraft"
            aria-label="Review title"
            @blur="saveRename"
          />
        </form>
        <button
          v-else
          type="button"
          class="review-title-button"
          :disabled="!canRename"
          @click="startRename"
        >
          {{ selectedTitle }}
        </button>
        <div class="button-row">
          <button
            type="button"
            :disabled="!canAnalyze"
            @click="analyzeSelected"
          >
            {{ isAnalysisActive ? "Analyzing" : "Analyze" }}
          </button>
          <button type="button" :disabled="!canExport" @click="exportSelected">
            Export
          </button>
          <button
            type="button"
            class="secondary-button"
            :disabled="!canPurge"
            @click="deleteSelected"
          >
            Delete
          </button>
        </div>
      </header>

      <div class="workspace-content">
        <RouterView v-slot="{ Component }">
          <component :is="Component" @open-settings="openSettings" />
        </RouterView>
      </div>
    </main>

    <aside
      v-if="showFindingsSidebar"
      class="findings-sidebar"
      :style="{
        width: `${findingsSidebar.renderedWidthRem.value}rem`,
        flexBasis: `${findingsSidebar.renderedWidthRem.value}rem`,
      }"
    >
      <button
        type="button"
        class="findings-resize-handle"
        aria-label="Resize findings sidebar"
        @pointerdown.stop="findingsSidebar.startResize"
      />
      <FindingsPanel
        class="findings-sidebar-panel"
        :layers="activeProjection?.layers ?? []"
        :allow-new-finding="canAddFinding"
        :allow-edit-review="canEditReview"
        :selected-layer-id="interaction.selectedLayerId"
        :review-options="activeProjection?.reviewOptions ?? null"
        :classification-options="activeProjection?.classificationOptions ?? []"
        @new-finding="openNewFinding"
        @select-layer="selectLayer"
        @update-finding="updateFinding"
        @update-layer="updateLayer"
      />
    </aside>

    <div
      v-if="interaction.creatingFinding"
      class="modal-backdrop"
      aria-hidden="true"
      @click.self="closeNewFinding"
    />

    <div
      v-if="settingsOpen"
      class="modal-backdrop"
      @click.self="settingsOpen = false"
    >
      <section
        class="settings-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
      >
        <div class="section-head">
          <h2 id="settings-title">Settings</h2>
          <button
            type="button"
            class="icon-button"
            aria-label="Close settings"
            @click="settingsOpen = false"
          >
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        </div>
        <div
          class="settings-tabs"
          role="tablist"
          aria-label="Settings sections"
        >
          <button
            type="button"
            role="tab"
            :aria-selected="settingsSection === 'models'"
            :class="{ active: settingsSection === 'models' }"
            @click="settingsSection = 'models'"
          >
            Models
          </button>
          <button
            type="button"
            role="tab"
            :aria-selected="settingsSection === 'policies'"
            :class="{ active: settingsSection === 'policies' }"
            @click="settingsSection = 'policies'"
          >
            Policies
          </button>
          <button
            type="button"
            role="tab"
            :aria-selected="settingsSection === 'dependencies'"
            :class="{ active: settingsSection === 'dependencies' }"
            @click="settingsSection = 'dependencies'"
          >
            Dependencies
          </button>
        </div>
        <ModelSettingsPanel v-if="settingsSection === 'models'" unified />
        <InstructionSetSettingsPanel
          v-else-if="settingsSection === 'policies'"
        />
        <DependenciesSettingsPanel v-else />
      </section>
    </div>

    <div
      v-if="newFindingOpen"
      class="modal-backdrop"
      @click.self="closeNewFinding"
    >
      <section
        class="settings-modal finding-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-finding-title"
      >
        <div class="section-head">
          <h2 id="new-finding-title">New finding</h2>
          <button
            type="button"
            class="icon-button"
            aria-label="Close new finding"
            @click="closeNewFinding"
          >
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        </div>
        <form class="grid-form finding-form" @submit.prevent="saveNewFinding">
          <label>
            Label
            <input v-model="newFinding.label" required />
          </label>
          <label>
            Entity type
            <select v-model="newFinding.reviewed_entity_type" required>
              <option value="" disabled>Select a classification</option>
              <option
                v-for="option in activeProjection?.classificationOptions ?? []"
                :key="option.entity_type"
                :value="option.entity_type"
              >
                {{ option.display_name }}
              </option>
            </select>
          </label>
          <label class="form-wide">
            Description
            <textarea v-model="newFinding.description" required rows="4" />
          </label>
          <label class="form-wide">
            Reason
            <textarea v-model="newFinding.reason" required rows="4" />
          </label>
          <div class="button-row form-actions">
            <button type="submit" :disabled="!canAddFinding">Add finding</button>
            <button
              type="button"
              class="secondary-button"
              @click="closeNewFinding"
            >
              Cancel
            </button>
          </div>
        </form>
      </section>
    </div>

    <NotificationStack />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { storeToRefs } from "pinia";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { api } from "./api/client";
import type {
  FindingTarget,
  FindingUpdateRequest,
  LayerUpdateRequest,
  Session,
} from "./api/contracts";
import { isPdfDocumentSource } from "./api/contracts";
import DependenciesSettingsPanel from "./components/DependenciesSettingsPanel.vue";
import FindingsPanel from "./components/FindingsPanel.vue";
import InstructionSetSettingsPanel from "./components/InstructionSetSettingsPanel.vue";
import NotificationStack from "./components/NotificationStack.vue";
import ModelSettingsPanel from "./components/ModelSettingsPanel.vue";
import { useResizableWidth } from "./composables/useResizableWidth";
import { useNotificationsStore } from "./stores/notifications";
import { useSessionsStore } from "./stores/sessions";

type Theme = "light" | "dark";
type SettingsSection = "models" | "policies" | "dependencies";
interface NewFindingDraft {
  label: string;
  reviewed_entity_type: string;
  description: string;
  reason: string;
  target: FindingTarget | null;
}

const savedTheme = window.localStorage.getItem("aiadr-theme");
const theme = ref<Theme>(savedTheme === "light" ? "light" : "dark");
const settingsOpen = ref(false);
const settingsSection = ref<SettingsSection>("models");
const newFindingOpen = ref(false);
const renaming = ref(false);
const renameDraft = ref("");
const renameInput = ref<HTMLInputElement | null>(null);
const newFinding = ref<NewFindingDraft>({
  label: "",
  reviewed_entity_type: "",
  description: "",
  reason: "",
  target: null,
});
const sessions = useSessionsStore();
const {
  activeProjection,
  activeSession,
  activeSessionId,
  canAddFinding,
  canAnalyze,
  canEditReview,
  canExport,
  canPurge,
  canRename,
  interaction,
  isAnalysisActive,
  isSessionsLoading,
  sessions: sessionItems,
} = storeToRefs(sessions);
const notifications = useNotificationsStore();
const route = useRoute();
const router = useRouter();
const reviewSidebar = useResizableWidth({
  storageKey: "aiadr-sidebar-width",
  defaultWidth: 18,
  minimumWidth: 6.25,
  collapseThreshold: 11,
  collapsedWidth: 6.25,
});
const findingsSidebar = useResizableWidth({
  storageKey: "aiadr-findings-width",
  defaultWidth: 26,
  minimumWidth: 18,
  maximumWidth: 40,
  direction: "left",
});

const routeSessionId = computed(() =>
  typeof route.params.sessionId === "string" ? route.params.sessionId : null,
);
const selectedTitle = computed(() => {
  const session =
    activeSession.value ??
    sessionItems.value.find(
      (item) => item.session_id === routeSessionId.value,
    );
  return session ? reviewTitle(session) : "Review session";
});
const selectedSessionLoaded = computed(() =>
  Boolean(
    routeSessionId.value && activeSessionId.value === routeSessionId.value,
  ),
);
const showReviewActions = computed(() => selectedSessionLoaded.value);
const showFindingsSidebar = computed(() => selectedSessionLoaded.value);
watch(
  theme,
  (value) => {
    document.documentElement.dataset.theme = value;
    window.localStorage.setItem("aiadr-theme", value);
  },
  { immediate: true },
);

watch(
  () => interaction.value.newFindingTarget,
  (target) => {
    if (!target) return;
    newFinding.value.target = target;
    newFindingOpen.value = true;
  },
);

onMounted(() => {
  void sessions.loadSessions();
});

function reviewTitle(session: Session) {
  const filename = session.source.file.filename;
  return session.display_name || filename.replace(/\.[^.]+$/, "") || filename;
}

function reviewLocation(sessionId: string) {
  return `/review/${sessionId}`;
}

function toggleTheme() {
  theme.value = theme.value === "dark" ? "light" : "dark";
}

function openSettings(section: SettingsSection = "models") {
  settingsSection.value = section;
  settingsOpen.value = true;
}

function goHome() {
  newReview();
}

function newReview() {
  sessions.clearActiveSession();
  void router.push("/");
}

function startRename() {
  if (!canRename.value) return;
  renameDraft.value = selectedTitle.value;
  renaming.value = true;
  void nextTick(() => renameInput.value?.focus());
}

async function saveRename() {
  if (!renaming.value) return;
  renaming.value = false;
  const name = renameDraft.value.trim();
  if (!name || name === selectedTitle.value) return;
  await sessions.renameActiveSession(name);
}

async function deleteSelected() {
  const deletedId = routeSessionId.value;
  if (!deletedId || !canPurge.value) return;
  const confirmed = window.confirm(
    "Permanently delete this review, its uploaded file, findings, effects, logs, exports, and audit history? This cannot be undone.",
  );
  if (!confirmed) return;
  const adjacentId = await sessions.purgeActiveSession();
  if (routeSessionId.value !== deletedId) return;
  await router.push(adjacentId ? reviewLocation(adjacentId) : "/");
}

async function analyzeSelected() {
  await sessions.requestAnalysis();
}

async function exportSelected() {
  const sessionId = activeSessionId.value;
  if (!sessionId) return;
  const created = await sessions.createExport();
  if (created) downloadExport(sessionId, created.filename);
}

function downloadExport(sessionId: string, filename: string) {
  const link = document.createElement("a");
  link.href = api.exportUrl(sessionId);
  link.download = filename;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
}

async function updateLayer(layerId: string, updates: LayerUpdateRequest) {
  await sessions.updateLayer(layerId, updates);
}

async function updateFinding(findingId: string, updates: FindingUpdateRequest) {
  await sessions.updateFinding(findingId, updates);
}

function selectLayer(layerId: string) {
  sessions.selectLayer(layerId);
}

function openNewFinding() {
  const session = activeSession.value;
  if (
    !session ||
    !activeProjection.value?.classificationOptions.length ||
    !canAddFinding.value
  )
    return;
  newFinding.value = {
    label: "",
    reviewed_entity_type: "",
    description: "",
    reason: "",
    target: null,
  };
  switch (session.source.kind) {
    case "audio":
      notifications.info("Select a sound range");
      break;
    case "image":
      notifications.info("Draw a region");
      break;
    case "document":
      notifications.info(
        isPdfDocumentSource(session.source)
          ? "Draw a region"
          : "Select text or draw a region within a picture",
      );
      break;
  }
  sessions.beginFindingTarget();
}

function closeNewFinding() {
  newFindingOpen.value = false;
  sessions.cancelFindingTarget();
}

async function saveNewFinding() {
  if (!activeSession.value) return;
  const draft = newFinding.value;
  const target = draft.target;
  if (!target) return;
  const added = await sessions.addFinding({
    label: draft.label.trim(),
    reviewed_entity_type: draft.reviewed_entity_type,
    description: draft.description.trim(),
    reason: draft.reason.trim(),
    target,
  });
  if (!added) return;
  newFindingOpen.value = false;
  sessions.cancelFindingTarget();
}
</script>
