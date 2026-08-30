<template>
  <div class="loading-spinner" role="status" aria-live="polite" :aria-label="label">
    <span class="loading-spinner-graphic" aria-hidden="true" />
  </div>
</template>

<script setup lang="ts">
defineProps<{
  label: string;
}>();
</script>

<style scoped>
.loading-spinner {
  display: grid;
  place-items: center;
}

.loading-spinner-graphic {
  width: 3rem;
  height: 3rem;
  border: 4px solid color-mix(in srgb, var(--overlay-border-color) 26%, transparent);
  border-top-color: var(--overlay-border-color);
  border-radius: 50%;
  animation: loading-spinner-spin 0.75s linear infinite;
}

@media (prefers-reduced-motion: reduce) {
  .loading-spinner-graphic {
    animation-duration: 1.5s;
  }
}

@keyframes loading-spinner-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
