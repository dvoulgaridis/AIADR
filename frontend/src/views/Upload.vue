<template>
  <section class="page upload-page">
    <div>
      <h1>Select a file to review</h1>
    </div>
    <FileDropzone @selected="selected = $event" />
    <div class="upload-controls">
      <button
        type="button"
        class="upload-control-button"
        :disabled="!selected || submitting"
        @click="submit"
      >
        {{ submitting ? "Submitting" : "Submit" }}
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import FileDropzone from "../components/FileDropzone.vue";
import { useSessionsStore } from "../stores/sessions";

const selected = ref<File | null>(null);
const submitting = ref(false);
const router = useRouter();
const sessions = useSessionsStore();

async function submit() {
  if (!selected.value || submitting.value) return;
  submitting.value = true;
  try {
    const sessionId = await sessions.upload(selected.value);
    if (sessionId) await router.push(`/review/${sessionId}`);
  } finally {
    submitting.value = false;
  }
}
</script>
