<template>
  <div
    ref="host"
    class="image-region-layer"
    :class="{ 'creating-target': creatingFinding }"
    @pointerdown="startNewTarget"
  >
    <div
      v-if="newTarget"
      class="overlay selected"
      :style="styleForRegion(newTarget)"
    />
    <div
      v-for="layer in surfaceLayers"
      :key="layer.id"
      class="overlay"
      :class="[effectClass(layer), { selected: isSelected(layer) }]"
      :style="styleForLayer(layer)"
      @pointerdown.stop="startEdit('move', layer, $event)"
    >
      <img
        v-if="pixelatedPreviews[layer.id]"
        class="overlay-pixel-preview"
        alt=""
        aria-hidden="true"
        :src="pixelatedPreviews[layer.id]"
      />
      <button
        v-if="editable && isSelected(layer)"
        class="overlay-resize-handle"
        type="button"
        aria-label="Resize target region"
        :style="{ cursor: resizeCursor(layer) }"
        @pointerdown.stop="startEdit('resize', layer, $event)"
      />
      <button
        v-if="editable && allowRotation && isSelected(layer)"
        class="overlay-rotate-handle"
        type="button"
        aria-label="Rotate target region"
        @pointerdown.stop="startEdit('rotate', layer, $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import type {
  FindingUpdateRequest,
  ImageSurface,
  Layer,
  TargetRegion,
} from "../api/contracts";
import { isImageTarget } from "../api/contracts";

const MIN_REGION_SIZE = 0.02;

const props = withDefaults(defineProps<{
  layers: Layer[];
  selectedLayerId: string | null;
  creatingFinding: boolean;
  editable?: boolean;
  surface: ImageSurface;
  allowRotation?: boolean;
  coordinateRotationDegrees?: number;
  showEffects?: boolean;
  pixelatedPreviews?: Record<string, string>;
}>(), {
  allowRotation: true,
  editable: true,
  coordinateRotationDegrees: 0,
  showEffects: true,
  pixelatedPreviews: () => ({}),
});

const emit = defineEmits<{
  "create-target": [region: TargetRegion];
  "select-layer": [layerId: string];
  "update-finding": [findingId: string, updates: FindingUpdateRequest];
}>();

const host = ref<HTMLElement | null>(null);
const newTarget = ref<TargetRegion | null>(null);
const draftRegions = ref<Record<string, TargetRegion>>({});
let stopPointerTracking: (() => void) | null = null;
let pendingDraftLayerId: string | null = null;

const surfaceLayers = computed(() => props.layers.filter((layer) => {
  const target = layer.finding.target;
  return isImageTarget(target)
    && surfacesMatch(target.surface, props.surface)
    && layer.enabled
    && layer.action !== "preserve";
}));

watch(() => props.creatingFinding, (active) => {
  if (!active) newTarget.value = null;
});

watch(() => props.editable, (editable, wasEditable) => {
  if (editable && wasEditable === false && pendingDraftLayerId) {
    clearDraftRegion(pendingDraftLayerId);
    pendingDraftLayerId = null;
  }
});

onBeforeUnmount(() => stopPointerTracking?.());

function surfacesMatch(left: ImageSurface, right: ImageSurface): boolean {
  if (left.type !== right.type) return false;
  if (left.type === "pdf_page" && right.type === "pdf_page") return left.page === right.page;
  if (left.type === "docx_picture" && right.type === "docx_picture") {
    return left.occurrence_id === right.occurrence_id;
  }
  return left.type === "file" && right.type === "file";
}

function regionFor(layer: Layer): TargetRegion | null {
  if (!isImageTarget(layer.finding.target)) return null;
  return draftRegions.value[layer.id] ?? layer.finding.target.region;
}

function styleForLayer(layer: Layer) {
  const region = regionFor(layer);
  if (!region) return {};
  const style = styleForRegion(region);
  return props.showEffects
    && layer.finding.review_decision === "confirmed"
    && layer.effect === "box"
    ? { ...style, backgroundColor: layer.fill_color }
    : style;
}

function styleForRegion(region: TargetRegion) {
  return {
    left: `${region.x * 100}%`,
    top: `${region.y * 100}%`,
    width: `${region.width * 100}%`,
    height: `${region.height * 100}%`,
    transform: `rotate(${region.rotation_degrees}deg)`,
  };
}

function effectClass(layer: Layer): string {
  return props.showEffects && layer.finding.review_decision === "confirmed"
    ? `overlay-effect-${layer.effect}`
    : "";
}

function isSelected(layer: Layer): boolean {
  return layer.id === props.selectedLayerId;
}

function startNewTarget(event: PointerEvent) {
  const container = host.value;
  if (!props.creatingFinding || !container || event.target !== container) return;
  event.preventDefault();
  const start = pointerPosition(event, container);
  const startX = start.x;
  const startY = start.y;
  let latest = boundedRegion(startX, startY, startX, startY);
  newTarget.value = latest;

  trackPointer(
    (moveEvent) => {
      const point = pointerPosition(moveEvent, container);
      latest = boundedRegion(
        startX,
        startY,
        point.x,
        point.y,
      );
      newTarget.value = latest;
    },
    () => {
      newTarget.value = null;
      emit("create-target", latest);
    },
    () => {
      newTarget.value = null;
    },
  );
}

function startEdit(mode: "move" | "resize" | "rotate", layer: Layer, event: PointerEvent) {
  if (!isSelected(layer)) {
    emit("select-layer", layer.id);
    return;
  }
  if (!props.editable) return;
  const target = layer.finding.target;
  const container = host.value;
  const initial = regionFor(layer);
  if (!isImageTarget(target) || !container || !initial) return;

  event.preventDefault();
  const overlay = (event.currentTarget as HTMLElement).closest<HTMLElement>(".overlay");
  const overlayBounds = overlay?.getBoundingClientRect();
  const startX = event.clientX;
  const startY = event.clientY;
  const centerX = overlayBounds ? overlayBounds.left + overlayBounds.width / 2 : startX;
  const centerY = overlayBounds ? overlayBounds.top + overlayBounds.height / 2 : startY;
  const startAngle = Math.atan2(startY - centerY, startX - centerX);
  const resizeState = mode === "resize"
    ? createResizeState(initial, surfacePoint(event, container), container)
    : null;
  let latest = { ...initial };

  trackPointer(
    (moveEvent) => {
      if (mode === "rotate") {
        const angle = Math.atan2(moveEvent.clientY - centerY, moveEvent.clientX - centerX);
        latest = {
          ...initial,
          rotation_degrees: normalizeDegrees(
            initial.rotation_degrees + ((angle - startAngle) * 180) / Math.PI,
          ),
        };
      } else {
        if (mode === "resize" && resizeState) {
          latest = resizeRegion(initial, surfacePoint(moveEvent, container), container, resizeState);
        } else {
          const delta = pointerDelta(moveEvent, startX, startY, container);
          latest = {
            ...initial,
            x: clamp(initial.x + delta.x, 0, 1 - initial.width),
            y: clamp(initial.y + delta.y, 0, 1 - initial.height),
          };
        }
      }
      draftRegions.value = { ...draftRegions.value, [layer.id]: latest };
    },
    () => {
      if (!regionsMatch(latest, initial)) {
        pendingDraftLayerId = layer.id;
        emit("update-finding", layer.finding.id, {
          target: { kind: "image", surface: target.surface, region: latest },
        });
      } else {
        clearDraftRegion(layer.id);
      }
    },
    () => {
      clearDraftRegion(layer.id);
      if (pendingDraftLayerId === layer.id) pendingDraftLayerId = null;
    },
  );
}

function trackPointer(
  onMove: (event: PointerEvent) => void,
  onUp: () => void,
  onCancel: () => void = () => {},
) {
  stopPointerTracking?.();
  const cleanup = () => {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", finish);
    window.removeEventListener("pointercancel", cancel);
    stopPointerTracking = null;
  };
  const finish = () => {
    cleanup();
    onUp();
  };
  const cancel = () => {
    cleanup();
    onCancel();
  };
  stopPointerTracking = cancel;
  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", finish, { once: true });
  window.addEventListener("pointercancel", cancel, { once: true });
}

function boundedRegion(startX: number, startY: number, endX: number, endY: number): TargetRegion {
  const x = Math.min(startX, endX);
  const y = Math.min(startY, endY);
  return {
    x: clamp(x, 0, 1 - MIN_REGION_SIZE),
    y: clamp(y, 0, 1 - MIN_REGION_SIZE),
    width: clamp(Math.abs(endX - startX), MIN_REGION_SIZE, 1 - x),
    height: clamp(Math.abs(endY - startY), MIN_REGION_SIZE, 1 - y),
    rotation_degrees: 0,
  };
}

function pointerPosition(event: PointerEvent, container: HTMLElement) {
  const width = container.offsetWidth || 1;
  const height = container.offsetHeight || 1;
  const point = surfacePoint(event, container);
  return {
    x: clamp(point.x / width, 0, 1),
    y: clamp(point.y / height, 0, 1),
  };
}

function surfacePoint(event: PointerEvent, container: HTMLElement) {
  const bounds = container.getBoundingClientRect();
  const width = container.offsetWidth || bounds.width;
  const height = container.offsetHeight || bounds.height;
  const centerX = bounds.left + bounds.width / 2;
  const centerY = bounds.top + bounds.height / 2;
  const point = rotateVector(
    event.clientX - centerX,
    event.clientY - centerY,
    -props.coordinateRotationDegrees,
  );
  return {
    x: point.x + width / 2,
    y: point.y + height / 2,
  };
}

function createResizeState(
  region: TargetRegion,
  pointer: { x: number; y: number },
  container: HTMLElement,
) {
  const containerWidth = container.offsetWidth || 1;
  const containerHeight = container.offsetHeight || 1;
  const width = region.width * containerWidth;
  const height = region.height * containerHeight;
  const center = {
    x: (region.x + region.width / 2) * containerWidth,
    y: (region.y + region.height / 2) * containerHeight,
  };
  const xAxis = rotateVector(1, 0, region.rotation_degrees);
  const yAxis = rotateVector(0, 1, region.rotation_degrees);
  const fixedCorner = {
    x: center.x - xAxis.x * width / 2 - yAxis.x * height / 2,
    y: center.y - xAxis.y * width / 2 - yAxis.y * height / 2,
  };
  const movingCorner = {
    x: center.x + xAxis.x * width / 2 + yAxis.x * height / 2,
    y: center.y + xAxis.y * width / 2 + yAxis.y * height / 2,
  };
  return {
    fixedCorner,
    xAxis,
    yAxis,
    grabOffset: {
      x: pointer.x - movingCorner.x,
      y: pointer.y - movingCorner.y,
    },
  };
}

function resizeRegion(
  initial: TargetRegion,
  pointer: { x: number; y: number },
  container: HTMLElement,
  state: ReturnType<typeof createResizeState>,
): TargetRegion {
  const containerWidth = container.offsetWidth || 1;
  const containerHeight = container.offsetHeight || 1;
  const handle = {
    x: pointer.x - state.grabOffset.x,
    y: pointer.y - state.grabOffset.y,
  };
  const offset = {
    x: handle.x - state.fixedCorner.x,
    y: handle.y - state.fixedCorner.y,
  };
  const widthPixels = clamp(
    dot(offset, state.xAxis),
    MIN_REGION_SIZE * containerWidth,
    containerWidth,
  );
  const heightPixels = clamp(
    dot(offset, state.yAxis),
    MIN_REGION_SIZE * containerHeight,
    containerHeight,
  );
  const center = {
    x: state.fixedCorner.x + state.xAxis.x * widthPixels / 2
      + state.yAxis.x * heightPixels / 2,
    y: state.fixedCorner.y + state.xAxis.y * widthPixels / 2
      + state.yAxis.y * heightPixels / 2,
  };
  const width = widthPixels / containerWidth;
  const height = heightPixels / containerHeight;
  return {
    ...initial,
    x: clamp((center.x - widthPixels / 2) / containerWidth, 0, 1 - width),
    y: clamp((center.y - heightPixels / 2) / containerHeight, 0, 1 - height),
    width,
    height,
  };
}

function pointerDelta(
  event: PointerEvent,
  startX: number,
  startY: number,
  container: HTMLElement,
) {
  const width = container.offsetWidth || 1;
  const height = container.offsetHeight || 1;
  const delta = rotateVector(
    event.clientX - startX,
    event.clientY - startY,
    -props.coordinateRotationDegrees,
  );
  return { x: delta.x / width, y: delta.y / height };
}

function rotateVector(x: number, y: number, degrees: number) {
  const radians = degrees * Math.PI / 180;
  return {
    x: x * Math.cos(radians) - y * Math.sin(radians),
    y: x * Math.sin(radians) + y * Math.cos(radians),
  };
}

function dot(left: { x: number; y: number }, right: { x: number; y: number }): number {
  return left.x * right.x + left.y * right.y;
}

function clearDraftRegion(layerId: string): void {
  if (!(layerId in draftRegions.value)) return;
  const next = { ...draftRegions.value };
  delete next[layerId];
  draftRegions.value = next;
}

function resizeCursor(layer: Layer): "nwse-resize" | "nesw-resize" {
  const rotation = (regionFor(layer)?.rotation_degrees ?? 0) + props.coordinateRotationDegrees;
  const angle = ((rotation % 180) + 180) % 180;
  return angle >= 45 && angle < 135 ? "nesw-resize" : "nwse-resize";
}

function regionsMatch(left: TargetRegion, right: TargetRegion): boolean {
  return Math.abs(left.x - right.x) < 0.0001
    && Math.abs(left.y - right.y) < 0.0001
    && Math.abs(left.width - right.width) < 0.0001
    && Math.abs(left.height - right.height) < 0.0001
    && Math.abs(left.rotation_degrees - right.rotation_degrees) < 0.01;
}

function normalizeDegrees(value: number): number {
  return ((value + 180) % 360 + 360) % 360 - 180;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}
</script>
