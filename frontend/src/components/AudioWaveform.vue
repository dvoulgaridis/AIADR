<template>
  <div class="audio-waveform">
    <div ref="waveformElement" class="audio-waveform-plot" />
    <div class="audio-transport">
      <button
        type="button"
        class="audio-play-button"
        :aria-label="playing ? 'Pause' : 'Play'"
        :disabled="!editable || loading || Boolean(error)"
        @click="togglePlayback"
      >
        <svg v-if="playing" aria-hidden="true" viewBox="0 0 24 24">
          <rect x="6" y="6" width="12" height="12" />
        </svg>
        <svg v-else aria-hidden="true" viewBox="0 0 24 24">
          <path d="m8 5 11 7-11 7Z" />
        </svg>
      </button>
      <span class="audio-time">
        {{ formatDurationSeconds(currentTime) }} / {{ formatDurationSeconds(duration) }}
      </span>
      <div class="audio-zoom-controls" aria-label="Waveform zoom controls">
        <button
          type="button"
          class="icon-button audio-zoom-button"
          aria-label="Zoom out waveform"
          :disabled="!editable || loading || Boolean(error) || zoomIndex === 0"
          @click="zoomOut"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
            <path d="M8 11h6" />
          </svg>
        </button>
        <button
          type="button"
          class="icon-button audio-zoom-button"
          aria-label="Zoom in waveform"
          :disabled="!editable || loading || Boolean(error) || zoomIndex === ZOOM_LEVELS.length - 1"
          @click="zoomIn"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
            <path d="M11 8v6" />
            <path d="M8 11h6" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin, { type Region } from "wavesurfer.js/dist/plugins/regions.esm.js";
import TimelinePlugin from "wavesurfer.js/dist/plugins/timeline.esm.js";
import type {
  FindingTarget,
  FindingUpdateRequest,
  Layer,
} from "../api/contracts";
import { isAudioTarget } from "../api/contracts";
import { isAbortError } from "../api/errors";
import { useNotificationsStore } from "../stores/notifications";
import { formatDurationSeconds } from "../utils/duration";

const ZOOM_LEVELS = [1, 2, 4, 8, 16] as const;

const props = defineProps<{
  src: string;
  layers: Layer[];
  selectedLayerId: string | null;
  creatingFinding: boolean;
  editable: boolean;
}>();
const emit = defineEmits<{
  "create-target": [target: FindingTarget];
  "loading-change": [loading: boolean];
  "select-layer": [layerId: string];
  "update-finding": [findingId: string, updates: FindingUpdateRequest];
}>();

const waveformElement = ref<HTMLElement | null>(null);
const currentTime = ref(0);
const duration = ref(0);
const playing = ref(false);
const loading = ref(true);
const error = ref("");
const zoomIndex = ref(0);
const notifications = useNotificationsStore();
const audioLayers = computed(() =>
  props.layers.filter((layer) => isAudioTarget(layer.finding.target)),
);

watch(
  loading,
  (value) => emit("loading-change", value),
  { immediate: true },
);

let waveSurfer: WaveSurfer | null = null;
let regions: RegionsPlugin | null = null;
let disableDragSelection: (() => void) | null = null;
let synchronizingRegions = false;
let loadSequence = 0;
let loadController: AbortController | null = null;
const subscriptions: Array<() => void> = [];

onMounted(() => {
  if (!waveformElement.value) return;
  regions = RegionsPlugin.create();
  waveSurfer = WaveSurfer.create({
    container: waveformElement.value,
    plugins: [
      regions,
      TimelinePlugin.create({
        height: 20,
        formatTimeCallback: formatDurationSeconds,
        style: { color: "#6b7280", fontSize: "11px" },
      }),
    ],
    height: 136,
    waveColor: "#73808c",
    progressColor: "#238277",
    cursorColor: "#facc15",
    cursorWidth: 2,
    normalize: true,
    interact: props.editable && !props.creatingFinding,
    dragToSeek: props.editable && !props.creatingFinding,
  });

  subscriptions.push(
    waveSurfer.on("play", () => {
      playing.value = true;
    }),
    waveSurfer.on("pause", () => {
      playing.value = false;
    }),
    waveSurfer.on("finish", () => {
      playing.value = false;
    }),
    waveSurfer.on("timeupdate", (time) => {
      currentTime.value = time;
    }),
    regions.on("region-clicked", (region, event) => {
      event.stopPropagation();
      if (
        props.editable
        && audioLayers.value.some((layer) => layer.id === region.id)
      ) {
        emit("select-layer", region.id);
      }
    }),
    regions.on("region-updated", persistRegion),
    regions.on("region-created", (region) => {
      if (synchronizingRegions || !props.creatingFinding) return;
      const target: FindingTarget = {
        kind: "audio",
        range: {
          start_time: region.start,
          end_time: region.end,
        },
      };
      region.remove();
      emit("create-target", target);
    }),
  );
  configureDragSelection();
  void loadAudio();
});

onBeforeUnmount(() => {
  loadSequence += 1;
  loadController?.abort();
  disableDragSelection?.();
  for (const unsubscribe of subscriptions) unsubscribe();
  waveSurfer?.destroy();
  waveSurfer = null;
  regions = null;
});

watch(
  () => props.src,
  () => {
    void loadAudio();
  },
);

watch(
  () => [
    props.selectedLayerId,
    ...audioLayers.value.map((layer) => (
      `${layer.id}:${JSON.stringify(layer.finding.target)}:`
      + `${layer.enabled}:${layer.action}:${layer.effect}:${layer.finding.review_decision}`
    )),
  ].join("|"),
  syncRegions,
);

watch(
  () => props.selectedLayerId,
  revealSelectedRegion,
);

watch(
  () => props.creatingFinding,
  () => {
    updateWaveformInteraction();
    configureDragSelection();
  },
);

watch(
  () => props.editable,
  (editable, wasEditable) => {
    if (!editable) waveSurfer?.pause();
    updateWaveformInteraction();
    configureDragSelection();
    if (editable && wasEditable === false) {
      syncRegions();
    } else {
      updateRegionInteractivity();
    }
  },
);

async function loadAudio() {
  if (!waveSurfer || !props.src) return;
  const sequence = ++loadSequence;
  loadController?.abort();
  const controller = new AbortController();
  loadController = controller;
  const previousTime = waveSurfer.getCurrentTime();
  const resume = waveSurfer.isPlaying();
  const hadPreview = duration.value > 0;
  waveSurfer.pause();
  loading.value = true;
  error.value = "";
  try {
    const response = await fetch(props.src, { signal: controller.signal });
    if (!response.ok) {
      throw new Error(`Audio preview request failed with status ${response.status}.`);
    }
    const blob = await response.blob();
    if (sequence !== loadSequence) return;
    await waveSurfer.loadBlob(blob);
    if (sequence !== loadSequence) return;
    duration.value = waveSurfer.getDuration();
    waveSurfer.setTime(Math.min(previousTime, duration.value));
    currentTime.value = waveSurfer.getCurrentTime();
    applyZoom();
    syncRegions();
    revealSelectedRegion();
    if (resume) await waveSurfer.play();
  } catch (loadError) {
    if (sequence !== loadSequence || isAbortError(loadError)) return;
    const message = loadError instanceof Error
      ? loadError.message
      : "Audio preview could not be loaded.";
    if (!hadPreview) error.value = message;
    notifications.error(message);
  } finally {
    if (sequence === loadSequence) {
      loadController = null;
      loading.value = false;
    }
  }
}

function syncRegions() {
  if (!regions || !duration.value) return;
  synchronizingRegions = true;
  try {
    regions.clearRegions();
    for (const layer of audioLayers.value) {
      if (!isAudioTarget(layer.finding.target)) continue;
      const selected = layer.id === props.selectedLayerId;
      const effectActive = (
        layer.enabled
        && layer.action !== "preserve"
        && layer.finding.review_decision === "confirmed"
      );
      regions.addRegion({
        id: layer.id,
        start: layer.finding.target.range.start_time,
        end: layer.finding.target.range.end_time,
        drag: selected && props.editable,
        resize: selected && props.editable,
        minLength: 0.01,
        color: selected
          ? "rgb(250 204 21 / 35%)"
          : effectActive
            ? "rgb(220 38 38 / 24%)"
            : "rgb(107 114 128 / 22%)",
      });
    }
  } finally {
    synchronizingRegions = false;
  }
}

function updateRegionInteractivity() {
  if (!regions) return;
  for (const region of regions.getRegions()) {
    const editable = props.editable && region.id === props.selectedLayerId;
    region.setOptions({ drag: editable, resize: editable });
  }
}

function revealSelectedRegion() {
  if (!waveSurfer) return;
  const layer = audioLayers.value.find((item) => item.id === props.selectedLayerId);
  if (!layer || !isAudioTarget(layer.finding.target)) return;
  const range = layer.finding.target.range;
  waveSurfer.setScrollTime((range.start_time + range.end_time) / 2);
}

function configureDragSelection() {
  disableDragSelection?.();
  disableDragSelection = null;
  if (!regions || !props.editable || !props.creatingFinding) return;
  disableDragSelection = regions.enableDragSelection({
    color: "rgb(250 204 21 / 35%)",
    minLength: 0.01,
  });
}

function updateWaveformInteraction() {
  const enabled = props.editable && !props.creatingFinding;
  waveSurfer?.setOptions({ interact: enabled, dragToSeek: enabled });
}

function persistRegion(region: Region) {
  if (
    synchronizingRegions ||
    !props.editable ||
    region.id !== props.selectedLayerId
  ) return;
  const layer = audioLayers.value.find((item) => item.id === region.id);
  if (!layer || !isAudioTarget(layer.finding.target)) return;
  const current = layer.finding.target.range;
  if (
    Math.abs(current.start_time - region.start) < 0.001
    && Math.abs(current.end_time - region.end) < 0.001
  ) {
    return;
  }
  emit("update-finding", layer.finding.id, {
    target: {
      kind: "audio",
      range: {
        start_time: region.start,
        end_time: region.end,
      },
    },
  });
}

async function togglePlayback() {
  if (!props.editable || !waveSurfer || loading.value || error.value) return;
  try {
    await waveSurfer.playPause();
  } catch (playbackError) {
    notifications.error(
      playbackError instanceof Error
        ? playbackError.message
        : "Audio playback could not be started.",
    );
  }
}

function applyZoom() {
  if (!waveSurfer || !waveformElement.value || duration.value <= 0) return;
  const level = ZOOM_LEVELS[zoomIndex.value] ?? 1;
  const fitPixelsPerSecond = waveformElement.value.clientWidth / duration.value;
  waveSurfer.zoom(level === 1 ? 0 : fitPixelsPerSecond * level);
}

function zoomOut() {
  if (!props.editable || zoomIndex.value === 0) return;
  zoomIndex.value -= 1;
  applyZoom();
}

function zoomIn() {
  if (!props.editable || zoomIndex.value >= ZOOM_LEVELS.length - 1) return;
  zoomIndex.value += 1;
  applyZoom();
}
</script>
