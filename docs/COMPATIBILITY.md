# Taleprism 0.3.1 compatibility

Taleprism is the public name of the earlier 原页 / Storygal local project. Version 0.2.0 strengthens editable recovery, reference tracking and public example reconstruction while preserving existing projects and persisted identifiers.

| Identifier | Kept for compatibility |
| --- | --- |
| Python package and server | `storygal`, `storygal.app:app` |
| Configuration | `STORYGAL_DATA_DIR`, `STORYGAL_PORT`, `STORYGAL_LLM_*` and existing key aliases |
| Editable-project payload | `storygal-project` v2; v1 imports remain supported |
| Image task format | `storygal-image-tasks` v2; adds template metadata and ordered reference responsibilities |
| Browser state | Existing `storygal-project` and `storygal-reader:*` keys |
| Reader export | Existing meta marker, source directory and inventory names |
| Old macOS launchers | “打开原页.command” and “停止原页.command” continue working |

Product version 0.3.1, template version 0.2.0 and project format version 2 are separate. The new workbench imports old projects; older workbenches may reject newly added check and reference fields.

The UI remains Chinese. Native Windows startup is not implemented. Local synthesis is macOS-specific; playing already accepted audio is portable. Public examples omit system-generated demonstration audio. A downloaded project contains its author's production checks, not the recipient's final approval.

Large historical Chibi assets and packed ZIPs are not in the lightweight checkout. Existing local copies remain untouched. Missing optional sample packs now give a download/import instruction instead of an unhandled file error. The canonical Last Light reference images remain in source so the tutorial and release builder do not depend on an unpublished release.

## Reliability changes in 0.2.0

The current workbench continues to import v1/v2 editable projects. Unresolved production states can be restored for repair; file integrity and reference validation remain mandatory. Cloud voice model metadata is retained through migration.

Continuity checks now carry explicit outcomes and source/media dependency snapshots. Old records are preserved, but records without the newer evidence require reinspection before applying or publishing affected plan illustrations. New valid records survive migration without inheriting final delivery approval. This is backward import compatibility, not a promise that an older workbench understands newly exported check fields.

The continuity-check API now requires an explicit `decision` (`passed`, `rejected`, or `revoked`) and a reason of at least eight non-padding characters. Existing integrations must add the decision field. Restoring a valid character merge keeps historical references and marks affected checks for repair; it does not rewrite or approve the saved composition.

Reader delivery versions also record the production revision. Old completed ZIPs remain usable, while an outdated export cannot be approved as the current production state. Published v0.1.0 attachments remain unchanged; the online showcase moves to the separately versioned v0.2.0 Chibi reader after deployment verification.

External AI plan responses now require `project_id`, `base_plan_revision`, `source_sha256` and `plan`, copied from the exported task. `/production/validate` checks the original project and revision, not a client-supplied latest revision. Validation only creates a draft; explicit saving still checks that revision. Same-source results from another project and results made before a newer plan save are rejected. Legacy external responses missing these bindings must be regenerated from a new task or kept as manual reference; the workbench does not invent missing provenance. This does not change editable-project import or synchronous in-workbench AI generation.

## Changes in 0.3.0

Reader recovery, image retry, dialogue-audio lifecycle and reading-position persistence are hardened. Chibi story graphs are edition-bound and reveal evidence only through the current reading position; unsupported texts do not receive inferred graphs. Moving backward hides later relationships and outcomes again. Browser storage identifiers and existing project/source IDs remain unchanged.

Creator workflows add project backup/restore notices, individually revision-bound shot exchange, external character/dialogue tasks and explicit WebGAL simplification reports. External AI task downloads do not send content to a service; the user chooses whether and where to share them. Guided Last Light imports remain bound to one fixed public archive and checksum, never a user-provided URL.

The application and release artifacts advance to 0.3.0. The eight-template library stays at 0.2.0; editable project format v2, the Chibi 0.2 reconstruction recipe/review records, source hashes and persisted identifiers keep their existing versions. Existing 0.2 tags, release attachments and complete exports remain available.

## Changes in 0.3.1

Chibi directory/map disclosure and whole-chapter image browsing now follow the current reading position unless the reader deliberately reveals the full view. Simplified/Traditional search normalization leaves source bytes untouched. Illustration fit and display placement change presentation only, not source anchors, image bytes or stored reading IDs. Maker-only image lineage and paired-shot review ship with the examples; the fire-ship flag-color continuity gate is still `needs_revision`, not a repaired or approved output. Template-library 0.2.0, project-format v2 and the reviewed Chibi recipe/review versions remain unchanged.
