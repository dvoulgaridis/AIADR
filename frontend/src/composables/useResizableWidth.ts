import { computed, onBeforeUnmount, ref } from "vue";

interface ResizableWidthOptions {
  storageKey: string;
  defaultWidth: number;
  minimumWidth: number;
  maximumWidth?: number;
  direction?: "right" | "left";
  collapseThreshold?: number;
  collapsedWidth?: number;
}

function storedWidth(key: string, fallback: number): number {
  const value = Number(window.localStorage.getItem(key));
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

export function useResizableWidth(options: ResizableWidthOptions) {
  const widthRem = ref(storedWidth(options.storageKey, options.defaultWidth));
  const collapsed = computed(
    () =>
      options.collapseThreshold !== undefined &&
      widthRem.value < options.collapseThreshold,
  );
  const renderedWidthRem = computed(() =>
    collapsed.value && options.collapsedWidth !== undefined
      ? options.collapsedWidth
      : widthRem.value,
  );
  let stopResize: (() => void) | null = null;

  function startResize(event: PointerEvent): void {
    event.preventDefault();
    stopResize?.();

    const rootFontSize =
      Number.parseFloat(
        window.getComputedStyle(document.documentElement).fontSize,
      ) || 16;
    const startX = event.clientX;
    const startWidth = renderedWidthRem.value;

    const onMove = (moveEvent: PointerEvent) => {
      const direction = options.direction === "left" ? -1 : 1;
      const delta =
        ((moveEvent.clientX - startX) / rootFontSize) * direction;
      const maximum = options.maximumWidth ?? Number.POSITIVE_INFINITY;
      let width = Math.max(
        options.minimumWidth,
        Math.min(maximum, startWidth + delta),
      );
      if (
        options.collapseThreshold !== undefined &&
        options.collapsedWidth !== undefined &&
        width < options.collapseThreshold
      ) {
        width = options.collapsedWidth;
      }
      widthRem.value = width;
    };
    const onUp = () => {
      window.localStorage.setItem(options.storageKey, String(widthRem.value));
      stopResize?.();
    };

    stopResize = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      stopResize = null;
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp, { once: true });
  }

  onBeforeUnmount(() => stopResize?.());

  return { collapsed, renderedWidthRem, startResize, widthRem };
}
