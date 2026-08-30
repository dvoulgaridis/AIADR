<template>
  <section class="panel model-log-panel">
    <h2>Analysis Log</h2>
    <p v-if="!logs.length" class="muted">No model calls logged yet.</p>
    <article v-for="log in logs" :key="log.log_id" class="list-item">
      <strong>{{ log.model || "Model" }}</strong>
      <span>
        {{ formatLabel(log.api_format) }} · {{ log.kind }} · {{ log.status }} ·
        {{ log.finish_reason || "no finish reason" }}
      </span>
      <span v-if="log.duration_ms !== null" class="muted">
        {{ formatDurationMilliseconds(log.duration_ms) }}
      </span>
      <span class="muted">
        request payload {{ log.request_summary.source_payload_bytes }} bytes
        <template v-if="log.request_summary.line_count !== null">
          · {{ log.request_summary.line_count }} lines ·
          {{ log.request_summary.character_count ?? 0 }} characters
        </template>
      </span>
      <span v-if="log.request_summary.attachment_kind" class="muted">
        {{ log.request_summary.attachment_kind }} attachment ·
        {{ log.request_summary.attachment_mime_type || "unknown type" }} ·
        {{ log.request_summary.attachment_size_bytes ?? 0 }} bytes
      </span>
      <span class="muted">
        response {{ log.result_summary.response_size_bytes ?? "N/A" }} bytes · parse
        {{ formatLabel(log.result_summary.parse_status) }}
        <template v-if="log.result_summary.parsed_finding_count !== null">
          · findings {{ log.result_summary.parsed_finding_count }} · rejected
          {{ log.result_summary.rejected_finding_count ?? 0 }}
        </template>
      </span>
      <span v-if="log.result_summary.provider_code" class="muted">
        provider code {{ log.result_summary.provider_code }} · status
        {{ log.result_summary.provider_status ?? "N/A" }} · request ID
        {{ log.result_summary.provider_request_id ?? "N/A" }}
      </span>
      <span v-if="preflightInputTokens(log) !== null" class="muted">
        {{ inputCountLabel(log) }} {{ preflightInputTokens(log) }} · requested max output
        tokens {{ log.requested_output_tokens ?? "N/A" }}
      </span>
      <span
        v-if="log.actual_input_tokens !== null || log.actual_output_tokens !== null"
        class="muted"
      >
        actual input tokens {{ log.actual_input_tokens ?? "?" }} · actual output tokens
        {{ log.actual_output_tokens ?? "?" }}
        <template v-if="log.reasoning_tokens !== null">
          · reasoning tokens {{ log.reasoning_tokens }}
        </template>
        · total tokens {{ log.total_tokens ?? "?" }}
      </span>
      <details v-if="log.debug">
        <summary>Request payload</summary>
        <pre>{{ formatDebugValue(log.debug.request_payload) }}</pre>
      </details>
      <details v-if="log.debug">
        <summary>Response content</summary>
        <pre>{{ responseContent(log.debug) }}</pre>
      </details>
    </article>
  </section>
</template>

<script setup lang="ts">
import type { DebugModelIO, ModelInteractionLog } from "../api/contracts";
import { formatDebugValue, formatDurationMilliseconds } from "../utils/duration";

defineProps<{ logs: ModelInteractionLog[] }>();

function preflightInputTokens(log: ModelInteractionLog): number | null {
  return log.provider_counted_input_tokens ?? log.estimated_input_tokens;
}

function inputCountLabel(log: ModelInteractionLog): string {
  return log.provider_counted_input_tokens !== null
    ? "provider-counted input tokens"
    : "estimated input tokens";
}

function responseContent(debug: DebugModelIO): string {
  if (debug.response_content) return formatDebugValue(debug.response_content);
  return debug.error_message || "(empty response)";
}

function formatLabel(value: string): string {
  return value.replaceAll("_", " ");
}
</script>
