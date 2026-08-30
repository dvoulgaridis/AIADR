# GDPR-Oriented Document Page Analysis

Analyze the rendered PDF page image for potential personal data. Use the supplied line index to
anchor findings to real PDF text.

Return one JSON object only, without Markdown fences or explanatory prose:

```json
{"findings":[{"entity_type":"name|email|phone|address|id_number|financial|health_data|unknown","data_subject_context":"adult|minor|unknown","label":"short human label","confidence":0.0,"page":1,"line_id":"l0001","exact_text":"exact sensitive text from the line","description":"what was detected","reason":"why it may be personal data"}]}
```

- Copy `exact_text` exactly from one supplied line and use the smallest continuous fragment.
- Return one finding per line when sensitive content spans lines.
- Do not return geometry, offsets, span IDs, policy classifications, actions, or effects.
- If visible sensitive content cannot be matched to a supplied line, omit its text anchor.
- Return `{"findings":[]}` when there are no findings.
