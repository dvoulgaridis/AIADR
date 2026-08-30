import { onBeforeUnmount } from "vue";
import { API_BASE } from "../api/client";
import type { AnalysisEvent } from "../api/contracts";

interface AnalysisEventCallbacks {
  onTerminal?: (event: AnalysisEvent) => void;
  onOpen?: (sessionId: string) => void;
}

const EVENT_TYPES = new Set(["progress", "complete", "error", "cancelled"]);

function isTerminal(event: AnalysisEvent): boolean {
  return (
    event.event_type === "complete" ||
    event.event_type === "error" ||
    event.event_type === "cancelled"
  );
}

function parseAnalysisEvent(data: string): AnalysisEvent {
  const value: unknown = JSON.parse(data);
  if (
    typeof value !== "object" ||
    value === null ||
    !("event_type" in value) ||
    typeof value.event_type !== "string" ||
    !EVENT_TYPES.has(value.event_type)
  ) {
    throw new Error("Received an invalid analysis event.");
  }
  return value as AnalysisEvent;
}

export function useAnalysisEvents(callbacks: AnalysisEventCallbacks = {}) {
  let source: EventSource | null = null;
  let connectionGeneration = 0;

  function disconnect() {
    connectionGeneration += 1;
    source?.close();
    source = null;
  }

  function connect(sessionId: string) {
    disconnect();

    const generation = connectionGeneration;
    const nextSource = new EventSource(`${API_BASE}/sessions/${sessionId}/events`);
    source = nextSource;

    function isCurrentConnection() {
      return source === nextSource && generation === connectionGeneration;
    }

    nextSource.onopen = () => {
      if (!isCurrentConnection()) return;
      callbacks.onOpen?.(sessionId);
    };

    function handleMessage(event: Event) {
      if (!isCurrentConnection()) return;
      try {
        const analysisEvent = parseAnalysisEvent(
          (event as MessageEvent<string>).data,
        );
        if (
          analysisEvent.session_id === sessionId &&
          isTerminal(analysisEvent)
        ) {
          callbacks.onTerminal?.(analysisEvent);
        }
      } catch {
        return;
      }
    }

    for (const name of EVENT_TYPES) {
      nextSource.addEventListener(name, handleMessage);
    }
  }

  onBeforeUnmount(disconnect);
  return { connect, disconnect };
}
