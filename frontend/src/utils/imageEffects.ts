interface NormalizedRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

export function renderPixelatedRegion(
  source: CanvasImageSource,
  sourceWidth: number,
  sourceHeight: number,
  region: NormalizedRegion,
): string | null {
  if (sourceWidth < 1 || sourceHeight < 1) return null;
  const x = Math.max(0, Math.min(sourceWidth - 1, Math.round(region.x * sourceWidth)));
  const y = Math.max(0, Math.min(sourceHeight - 1, Math.round(region.y * sourceHeight)));
  const width = Math.max(1, Math.min(sourceWidth - x, Math.round(region.width * sourceWidth)));
  const height = Math.max(1, Math.min(sourceHeight - y, Math.round(region.height * sourceHeight)));
  const small = document.createElement("canvas");
  small.width = Math.max(1, Math.floor(width / 12));
  small.height = Math.max(1, Math.floor(height / 12));
  const smallContext = small.getContext("2d");
  if (!smallContext) return null;
  smallContext.drawImage(source, x, y, width, height, 0, 0, small.width, small.height);

  const output = document.createElement("canvas");
  output.width = width;
  output.height = height;
  const outputContext = output.getContext("2d");
  if (!outputContext) return null;
  outputContext.imageSmoothingEnabled = false;
  outputContext.drawImage(small, 0, 0, small.width, small.height, 0, 0, width, height);
  return output.toDataURL("image/png");
}
