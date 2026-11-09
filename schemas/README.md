# Taleprism structured tasks

These schemas are generated from the workbench's Pydantic models. Do not maintain a second handwritten schema.

- `plan.schema.json`: a direction plan with scenes, objects, shots, acting and continuity.
- `plan-task.schema.json`: external AI response `{source_sha256, plan}`. The workbench export fixes the hash to the actual source and supplies available character IDs and paragraph byte offsets.

Use **章节制作方案 → 导出 AI 任务** for a particular project. Give the complete task to your tool and return its JSON through the workbench. Do not manually convert the paragraph labels in the human tutorial into byte offsets. References, evidence and dependencies are checked by the server in addition to structural validation. An imported AI response is a draft; it cannot grant approval or fabricate image IDs.

Product/template version: 0.1.0. Existing `storygal-image-tasks` and editable-project formats keep their own version 2 for compatibility. Legacy editable-project version 1 remains accepted.

Regenerate/check with `uv run --project backend python tools/export_prompt_kit.py [--check]`.
