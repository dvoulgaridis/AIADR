import { defineStore } from "pinia";

export type NotificationLevel = "info" | "success" | "warning" | "error";

export interface AppNotification {
  id: string;
  level: NotificationLevel;
  message: string;
}

const DEFAULT_DURATION_MS = 15000;
let nextNotificationId = 0;

export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message.trim()
    ? error.message
    : fallback;
}

export const useNotificationsStore = defineStore("notifications", {
  state: () => ({
    items: [] as AppNotification[],
  }),
  actions: {
    notify(
      message: string,
      level: NotificationLevel = "info",
      durationMs = DEFAULT_DURATION_MS,
    ): string {
      const normalized = message.trim();
      if (!normalized) return "";

      const existing = this.items.find(
        (notification) =>
          notification.level === level && notification.message === normalized,
      );
      if (existing) return existing.id;

      const id = `notification-${++nextNotificationId}`;
      this.items.unshift({ id, level, message: normalized });
      if (durationMs > 0) {
        window.setTimeout(() => this.dismiss(id), durationMs);
      }
      return id;
    },
    info(message: string, durationMs?: number) {
      return this.notify(message, "info", durationMs);
    },
    success(message: string, durationMs?: number) {
      return this.notify(message, "success", durationMs);
    },
    warning(message: string, durationMs?: number) {
      return this.notify(message, "warning", durationMs);
    },
    error(message: string, durationMs?: number) {
      return this.notify(message, "error", durationMs);
    },
    dismiss(id: string) {
      this.items = this.items.filter((notification) => notification.id !== id);
    },
  },
});
