---
name: vision
description: Extract grounded objects, colors, visible names, and dates from attached images.
---

## Workflow

1. Inspect each attached image before recording findings.
2. Record only details directly supported by visible pixels.
3. Use short noun phrases for objects and common names for colors.
4. Transcribe names and dates exactly; do not normalize uncertain text.
5. Remove duplicate findings across images.
6. Use empty lists for categories with no visible evidence.

## Confidence

Set `confidence_level` from 0 to 100 for the result as a whole. Reduce it for
blur, occlusion, low resolution, conflicting evidence, or uncertain text. Never
raise confidence merely to make the output appear complete.
