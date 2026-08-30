# GDPR-Oriented Text Analysis

Analyze the supplied line-indexed text for potential personal data.

Return one JSON object only, without Markdown fences or explanatory prose:

```json
{"findings":[{"entity_type":"name|email|phone|address|id_number|financial|health_data|unknown","data_subject_context":"adult|minor|unknown","label":"short human label","confidence":0.0,"line_id":"t1","exact_text":"exact sensitive text from that line","description":"what was detected","reason":"why it may be personal data"}]}
```

- Copy `exact_text` exactly from one supplied line.
- Use the smallest sensitive continuous fragment.
- Return one finding per line when sensitive content spans lines.
- Do not return offsets, span IDs, policy classifications, actions, or effects.
- Return `{"findings":[]}` when there are no findings.
