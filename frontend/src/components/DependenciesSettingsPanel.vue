<template>
  <section class="panel embedded-panel dependencies-panel">
    <div class="section-head">
      <h2>Dependencies</h2>
    </div>

    <dl v-if="dependencies.every((dependency) => dependency.status)" class="dependency-list">
      <div v-for="dependency in dependencies" :key="dependency.name">
        <dt>
          <strong>{{ dependency.name }}</strong>
          <span :class="['dependency-status', { available: dependency.status?.available }]">
            {{ dependency.status?.available ? "Available" : "Unavailable" }}
          </span>
        </dt>
        <dd>
          {{
            dependency.status?.version ||
            dependency.status?.error ||
            "No version information."
          }}
        </dd>
        <dd class="dependency-path">
          <span>Path</span>
          <code>{{ dependency.status?.path || "N/A" }}</code>
        </dd>
      </div>
    </dl>
    <p v-else class="muted">Checking dependencies...</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useModelsStore } from "../stores/models";

const store = useModelsStore();
const dependencies = computed(() => [
  { name: "FFmpeg", status: store.ffmpeg },
  { name: "LibreOffice", status: store.libreoffice },
]);

onMounted(() => {
  void store.loadDependencies();
});
</script>
