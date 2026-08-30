# CCPA/CPRA-Oriented Audio Analysis

Analyze the supplied audio context for audible personal information or sensitive personal information that may identify or be reasonably linked with a consumer or household.

Return one JSON object only, without Markdown fences or explanatory prose:

```json
{"findings":[{"entity_type":"name|email|phone|address|government_id|financial|account_credentials|online_identifier|precise_geolocation|biometric|health_data|minor_data|unknown","data_subject_context":"adult|minor|unknown","label":"short human label","confidence":0.0,"audio_range":{"start_time":0.0,"end_time":1.0},"description":"sanitized optional excerpt","reason":"why it may be personal information"}]}
```

- `start_time` is inclusive and `end_time` is exclusive.
- Timestamps are relative to the beginning of the attached audio, regardless of its position in the complete source.
- Do not return policy classifications, actions, or effects.
- Return `{"findings":[]}` when there are no audible findings.
