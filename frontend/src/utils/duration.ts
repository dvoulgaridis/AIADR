export const DURATION_TIMECODE_LABEL = "HH:MM:SS:mmm";
export const DURATION_TIMECODE_PATTERN = "\\d{2,}:[0-5]\\d:[0-5]\\d:\\d{3}";

const DURATION_TIMECODE_REGEX = /^(\d{2,}):([0-5]\d):([0-5]\d):(\d{3})$/;
const MILLISECONDS_PER_SECOND = 1_000;
const MILLISECONDS_PER_MINUTE = 60 * MILLISECONDS_PER_SECOND;
const MILLISECONDS_PER_HOUR = 60 * MILLISECONDS_PER_MINUTE;

export function formatDurationSeconds(seconds: number): string {
  if (!Number.isFinite(seconds)) return "00:00:00:000";
  return formatDurationMilliseconds(Math.max(0, seconds) * MILLISECONDS_PER_SECOND);
}

export function formatDurationMilliseconds(milliseconds: number): string {
  if (!Number.isFinite(milliseconds)) return "00:00:00:000";
  const total = Math.round(Math.max(0, milliseconds));
  const hours = Math.floor(total / MILLISECONDS_PER_HOUR);
  const minutes = Math.floor((total % MILLISECONDS_PER_HOUR) / MILLISECONDS_PER_MINUTE);
  const seconds = Math.floor((total % MILLISECONDS_PER_MINUTE) / MILLISECONDS_PER_SECOND);
  const remainder = total % MILLISECONDS_PER_SECOND;
  return [
    String(hours).padStart(2, "0"),
    String(minutes).padStart(2, "0"),
    String(seconds).padStart(2, "0"),
    String(remainder).padStart(3, "0"),
  ].join(":");
}

export function parseDurationTimecode(timecode: string): number | null {
  const match = DURATION_TIMECODE_REGEX.exec(timecode.trim());
  if (!match) return null;
  const [, hours, minutes, seconds, milliseconds] = match;
  const totalMilliseconds =
    Number(hours) * MILLISECONDS_PER_HOUR
    + Number(minutes) * MILLISECONDS_PER_MINUTE
    + Number(seconds) * MILLISECONDS_PER_SECOND
    + Number(milliseconds);
  return Number.isSafeInteger(totalMilliseconds)
    ? totalMilliseconds / MILLISECONDS_PER_SECOND
    : null;
}

function isSecondsDurationField(key: string): boolean {
  return key.endsWith("_seconds") || key === "start_time" || key === "end_time";
}

function isMillisecondsDurationField(key: string): boolean {
  return /(?:^|_)(?:duration|elapsed|latency)_ms$/.test(key);
}

function transformDurationFields(value: unknown, key = ""): unknown {
  if (typeof value === "number") {
    if (isSecondsDurationField(key)) return formatDurationSeconds(value);
    if (isMillisecondsDurationField(key)) return formatDurationMilliseconds(value);
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => transformDurationFields(item));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([childKey, childValue]) => [
        childKey,
        transformDurationFields(childValue, childKey),
      ]),
    );
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (
      (trimmed.startsWith("{") && trimmed.endsWith("}"))
      || (trimmed.startsWith("[") && trimmed.endsWith("]"))
    ) {
      try {
        return transformDurationFields(JSON.parse(trimmed));
      } catch {
        return value;
      }
    }
  }
  return value;
}

export function formatDebugValue(value: unknown): string {
  const formatted = transformDurationFields(value);
  if (typeof formatted === "string") return formatted;
  return JSON.stringify(formatted, null, 2) ?? String(formatted);
}
