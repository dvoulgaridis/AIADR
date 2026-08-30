<template>
  <section class="panel audit-panel">
    <h2>Audit</h2>
    <p v-if="lastEventHash" class="audit-hash">Last event hash: {{ lastEventHash }}</p>
    <p v-if="!events.length" class="muted">No audit events yet.</p>
    <ol v-else class="audit-list">
      <li v-for="event in events" :key="event.event_id">
        <strong>{{ event.event_type }}</strong>
        <span>{{ event.actor_type }} · {{ event.actor_id }}</span>
        <small>{{ event.created_at }}</small>
        <details v-if="Object.keys(event.payload).length">
          <summary>Event payload</summary>
          <pre>{{ formatDebugValue(event.payload) }}</pre>
        </details>
      </li>
    </ol>
  </section>
</template>

<script setup lang="ts">
import type { AuditEvent } from "../api/contracts";
import { formatDebugValue } from "../utils/duration";

defineProps<{ events: AuditEvent[]; lastEventHash: string | null }>();
</script>
