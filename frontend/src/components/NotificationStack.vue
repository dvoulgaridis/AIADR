<template>
  <TransitionGroup
    name="notification"
    tag="div"
    class="notification-stack"
    aria-live="polite"
    aria-relevant="additions removals"
  >
    <article
      v-for="notification in store.items"
      :key="notification.id"
      class="notification-panel"
      :data-level="notification.level"
      :role="notification.level === 'error' ? 'alert' : 'status'"
    >
      <p>{{ notification.message }}</p>
      <button
        type="button"
        class="notification-dismiss"
        aria-label="Dismiss notification"
        @click="store.dismiss(notification.id)"
      >
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path d="m6 6 12 12M18 6 6 18" />
        </svg>
      </button>
    </article>
  </TransitionGroup>
</template>

<script setup lang="ts">
import { useNotificationsStore } from "../stores/notifications";

const store = useNotificationsStore();
</script>
