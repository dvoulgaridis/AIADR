# GDPR-Oriented Image Analysis

Analyze the image for visible potential personal data.

Return one JSON object only, without Markdown fences or explanatory prose:

```json
{"findings":[{"entity_type":"face|minor_face|name|email|phone|address|id_number|financial|health_data|unknown","data_subject_context":"adult|minor|unknown","label":"short human label","confidence":0.0,"target_region":{"x":0.0,"y":0.0,"width":0.1,"height":0.1},"description":"what was detected","reason":"why it may be personal data"}]}
```

- Use normalized top-left-origin coordinates in `[0, 1]`.
- Do not return policy classifications, actions, or effects.
- Return `{"findings":[]}` when there are no visible findings.
