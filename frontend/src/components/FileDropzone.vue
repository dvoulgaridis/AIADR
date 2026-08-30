<template>
  <label class="dropzone">
    <input
      type="file"
      accept="image/jpeg,image/png,image/webp,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,audio/*,.aac,.flac,.m4a,.mp3,.mp4,.ogg,.opus,.wav,.webm,text/plain,text/csv,.txt,.csv,.docx"
      @change="onChange"
    />
    <span>Choose image, document, audio, or text file</span>
  </label>
</template>

<script setup lang="ts">
const emit = defineEmits<{ selected: [file: File] }>();

function onChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  emit("selected", file);
}
</script>
