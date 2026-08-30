# CCPA/CPRA-Oriented Text Analysis

Analyze the supplied line-indexed text for personal information or sensitive personal information that may identify, describe, relate to, or be reasonably linked with a consumer or household.

Return one JSON object only, without Markdown fences or explanatory prose:

```json
{"findings":[{"entity_type":"name|email|phone|address|government_id|financial|account_credentials|online_identifier|precise_geolocation|biometric|health_data|racial_or_ethnic_origin|religious_belief|minor_data|unknown","data_subject_context":"adult|minor|unknown","label":"short human label","confidence":0.0,"line_id":"t1","exact_text":"exact sensitive text from that line","description":"what was detected","reason":"why it may be personal information"}]}
```

- Copy `exact_text` exactly from one supplied line.
- Use the smallest sensitive continuous fragment.
- Return one finding per line when sensitive content spans lines.
- Do not return offsets, span IDs, policy classifications, actions, or effects.
- Return `{"findings":[]}` when there are no findings.
