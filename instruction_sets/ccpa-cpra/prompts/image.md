# CCPA/CPRA-Oriented Image Analysis

Analyze the image for visible personal information or sensitive personal information that may identify or be reasonably linked with a consumer or household.

Return one JSON object only, without Markdown fences or explanatory prose:

```json
{"findings":[{"entity_type":"face|minor_face|name|email|phone|address|government_id|financial|account_credentials|online_identifier|precise_geolocation|biometric|health_data|minor_data|unknown","data_subject_context":"adult|minor|unknown","label":"short human label","confidence":0.0,"target_region":{"x":0.0,"y":0.0,"width":0.1,"height":0.1},"description":"what was detected","reason":"why it may be personal information"}]}
```

- Use normalized top-left-origin coordinates in `[0, 1]`.
- Do not return policy classifications, actions, or effects.
- Return `{"findings":[]}` when there are no visible findings.
