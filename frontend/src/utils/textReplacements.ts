import type { Layer } from "../api/contracts";
import { isDocumentTarget } from "../api/contracts";

const SEPARATORS = new Set("@.-_+/() ");
const DIGITS = new Set("0123456789");

export function partialMask(value: string) {
  if (value.includes("@")) {
    const separator = value.indexOf("@");
    const local = value.slice(0, separator);
    const domain = value.slice(separator + 1);
    if (!local) return `*@${domain}`;
    return `${local.charAt(0)}${"*".repeat(Math.max(local.length - 1, 1))}@${domain}`;
  }

  const digitIndexes = [...value]
    .map((character, index) => (DIGITS.has(character) ? index : -1))
    .filter((index) => index >= 0);
  if (digitIndexes.length >= 5) {
    const keep = new Set(digitIndexes.slice(-4));
    return [...value]
      .map((character, index) =>
        DIGITS.has(character) && !keep.has(index) ? "*" : character,
      )
      .join("");
  }

  let tokenStart = true;
  return [...value]
    .map((character) => {
      if (SEPARATORS.has(character)) {
        tokenStart = true;
        return character;
      }
      if (tokenStart) {
        tokenStart = false;
        return character;
      }
      return "*";
    })
    .join("");
}

export function resolveTextReplacements(layers: Layer[]) {
  const selected = layers
    .filter(
      (layer) =>
        layer.enabled &&
        layer.action !== "preserve" &&
        layer.finding.review_decision === "confirmed" &&
        isDocumentTarget(layer.finding.target),
    )
    .sort((left, right) => {
      if (left.finding.id !== right.finding.id) {
        return left.finding.id < right.finding.id ? -1 : 1;
      }
      return left.id < right.id ? -1 : left.id > right.id ? 1 : 0;
    });

  const counters = new Map<string, number>();
  const tokens = new Map<string, string>();
  for (const layer of selected) {
    if (layer.effect !== "token_replace" || !isDocumentTarget(layer.finding.target)) continue;
    if (layer.custom_text?.trim()) continue;
    const entityType = layer.finding.effective_entity_type.toUpperCase();
    const key = `${entityType}\u0000${layer.finding.target.locator.exact_text}`;
    if (!tokens.has(key)) {
      const sequence = (counters.get(entityType) ?? 0) + 1;
      counters.set(entityType, sequence);
      tokens.set(key, `${entityType}_${sequence.toString().padStart(3, "0")}`);
    }
  }

  const replacements: Record<string, string> = {};
  for (const layer of selected) {
    if (!isDocumentTarget(layer.finding.target)) continue;
    const exactText = layer.finding.target.locator.exact_text;
    if (layer.effect === "box") {
      replacements[layer.id] = "[REDACTED]";
    } else if (layer.effect === "partial_mask") {
      replacements[layer.id] = partialMask(exactText);
    } else if (layer.effect === "token_replace") {
      const entityType = layer.finding.effective_entity_type.toUpperCase();
      const key = `${entityType}\u0000${exactText}`;
      if (layer.custom_text?.trim()) {
        replacements[layer.id] = layer.custom_text;
        continue;
      }
      const token = tokens.get(key);
      if (!token) throw new Error(`Missing text replacement for layer: ${layer.id}`);
      replacements[layer.id] = token;
    } else {
      throw new Error(`Unsupported document text effect: ${layer.effect}`);
    }
  }
  return replacements;
}
