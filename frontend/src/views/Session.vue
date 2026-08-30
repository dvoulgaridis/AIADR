<template>
  <section class="review-layout">
    <div class="review-grid">
      <ReviewCanvas
        :session="activeProjection?.session ?? null"
        :layers="activeProjection?.layers ?? []"
        :selected-layer-id="interaction.selectedLayerId"
        :analyzing="activeProjection?.session.analysis_active === true"
        :creating-finding="interaction.creatingFinding"
        :editable="canEditReview"
        @update-finding="sessions.updateFinding"
        @create-target="sessions.setFindingTarget"
        @select-layer="sessions.selectLayer"
      />
      <AnalysisLogPanel :logs="activeProjection?.modelLogs ?? []" />
      <AuditTrailPanel
        :events="activeProjection?.auditEvents ?? []"
        :last-event-hash="activeProjection?.lastEventHash ?? null"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from "vue";
import { storeToRefs } from "pinia";
import AnalysisLogPanel from "../components/AnalysisLogPanel.vue";
import AuditTrailPanel from "../components/AuditTrailPanel.vue";
import ReviewCanvas from "../components/ReviewCanvas.vue";
import { useAnalysisEvents } from "../composables/useAnalysisEvents";
import { useSessionsStore } from "../stores/sessions";

const props = defineProps<{ sessionId: string }>();
const sessions = useSessionsStore();
const { activeProjection, canEditReview, interaction } = storeToRefs(sessions);
const sessionId = computed(() => props.sessionId);
let hydrationController: AbortController | null = null;

function hydrateSession(requestedSessionId: string): void {
  hydrationController?.abort();
  const controller = new AbortController();
  hydrationController = controller;
  void sessions
    .loadActiveSession(requestedSessionId, controller.signal)
    .finally(() => {
      if (hydrationController === controller) hydrationController = null;
    });
}

const events = useAnalysisEvents({
  onTerminal: (event) => {
    if (event.session_id === sessionId.value) {
      hydrateSession(event.session_id);
    }
  },
  onOpen: (eventSessionId) => {
    if (eventSessionId === sessionId.value) {
      hydrateSession(eventSessionId);
    }
  },
});

watch(
  sessionId,
  (nextSessionId) => {
    events.connect(nextSessionId);
    hydrateSession(nextSessionId);
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  hydrationController?.abort();
  events.disconnect();
  sessions.clearActiveSession();
});
</script>
