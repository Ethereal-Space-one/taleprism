# Taleprism structured tasks

These schemas are generated from the workbench's Pydantic models. Do not maintain a second handwritten schema.

- `plan.schema.json`: a direction plan with scenes, objects, shots, acting and continuity.
- `plan-task.schema.json`: external AI response `{project_id, base_plan_revision, source_sha256, plan}`. The workbench export fixes the project, saved plan revision and source hash, and supplies available character IDs and paragraph byte offsets.

Use **章节制作方案 → 导出 AI 任务** for a particular project. Give the complete task to your tool and return its JSON through the workbench. Do not manually convert the paragraph labels in the human tutorial into byte offsets. References, evidence and dependencies are checked by the server in addition to structural validation. An imported AI response is a draft; it cannot grant approval or fabricate image IDs. Validation does not save it. The explicit save uses the task's original revision, so newer work cannot be silently replaced.

External responses must return the binding fields unchanged. A result from another project is rejected even if both projects contain the same source. If the plan changed after task export, export a new task instead of editing the old result's revision. Legacy responses without project/revision bindings are not automatically upgraded because their origin and age cannot be verified; retain them as manual reference or rerun a newly exported task. Editable-project v1/v2 recovery and the in-workbench synchronous AI generation route are unchanged. These fields bind a task snapshot; they are not proof of the model or author that produced the JSON.

Product/template version: 0.1.0. Existing `storygal-image-tasks` and editable-project formats keep their own version 2 for compatibility. Legacy editable-project version 1 remains accepted.

Regenerate/check with `uv run --project backend python tools/export_prompt_kit.py [--check]`.
