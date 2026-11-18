# Taleprism compatibility

## Current public version: 0.9.1

Reader ZIPs are offline publications with their own player. Editable ZIPs are a different format and may include internal working material. Two current public projects, Chibi and Last Light, retain their public work IDs and original source/media in their reissued readers; the separate reader-only demonstrations are not importable projects. See [release](RELEASE-v0.9.1.md) and [engineering history](ITERATION-HISTORY.md). The online Chibi showcase uses the published 0.9.1 reader. Old downloaded ZIPs keep their bundled reader; updating the site does not modify them.

## Historical 0.3.x formats

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

## Historical development 0.4.0 scene directions

Illustrations may optionally carry a bounded `motion` object. Missing means the existing exact-image demo behavior; explicit `null` means deliberately static. An unreviewed object remains an editable draft and renders static for readers. The object binds source SHA-256, original image SHA-256/dimensions and exact `after_byte`; evidence must already appear at that position. Rain requires an explicit wet-ground list, which may be empty only when ripple count is zero.

Current editable v1/v2 imports remain supported; old packages without motion do not gain inferred author approval. The bundle identifier and format remain v2. Older workbenches may reject or discard fields they do not understand; use this candidate to continue editing scene directions and retain a backup before using older software. Standalone readers contain their own runtime. Unchanged production reapplication preserves directions; a changed bound image or position requires explicit static/removal and a new review. No personal reading state, animation preference, credentials or new artwork is added to an export.

In the 0.4 development iteration, downloadable public examples were still on the earlier 0.3.x line; this was not a separate public release.

## Historical development 0.5.0: single-illustration projects

A single-illustration studio backup is an editable project **v3** ZIP with `project.single_plate_studio: true`. Restoring it creates a **new** project with a link back to its focused editor. This is a navigation hint, not acceptance of an asset, a direction or its artistic quality. It does not change the original text, an illustration’s source anchor or its review state. Ordinary projects still export as v2; v1/v2 bundles omit the field and still open in the full workbench. Use 0.5.0 or later to restore studio-specific ZIPs: older workbenches do not understand v3. Standalone reading ZIPs need no workbench.

## Historical development 0.6.0: paragraph narration

An editable project with narration history uses bundle v4; older v1/v2/v3 archives remain valid and gain no audio. Reader payload v4 is emitted only when a paragraph actually has accepted narration. These reads are manual and independent of character voices, captions, map data and illustration directions. Unplaced, rejected, or replaced voices are not part of a reader export. Restoring an editable project keeps the full private take history, credits and rights decisions, cross-checking source file hash, canonical UTF-8 hash, paragraph bounds/text and WAV digest. For public delivery, send the reading ZIP, **not** this editable backup. WebGAL export excludes independent paragraph recordings and explicitly warns about the difference.

## Historical development 0.6.1: working state versus reading materials

Old v1–v4 editable archives remain usable. A current archive with an actual editorial issue state uses v5. The new inventory declares the editorial issue count even when exactly zero. In old archives without this coverage marker, the app reports the history as unknown instead of reconstructing a clean bill of health. A final review remains separate from editing notes. The previous v0.6.0 standalone reader and editorial sample are not overwritten.

New reading JSON may contain a verified original whitespace gap before each block; the anchors and visible text runs are unchanged. Older readers can ignore these fields, and older data without the fields does not pretend to have a byte-exact original spacing layout. A reviewed motion is publicly projected into its renderer contract; its production observation and evidence remain with the editable project. Standalone readers include their matching runtime.

## Private 0.7.0: finite local soundscapes
Only reader payloads with an accepted paragraph soundscape move to v5; other editions do not acquire a synthetic track. Editable projects with actual soundscape history use v6, retain private evidence, decisions, audio and timeline choices, and restore their exact WAVs. The book needs no synthesizer at runtime. Independent narration, dialogue and reviewed picture motion continue to work. WebGAL warns that paragraph soundscapes are omitted. Previous readers remain intact; use the current workbench to edit the new project ZIPs.

## 0.9.1: source-bound edition decisions

The 0.9.0 Chibi reader correctly presented the curated illustration descriptions and two poem-safe reveal points. Importing its editable example created a new project ID as intended, but the ordinary reader export from that copy did not reproduce all twelve image descriptions or the two later reveal points. These decisions are not equivalent to changing the image file or its original source attachment. The release preserves the decisions across the import/export path without giving a new editable project the public reader’s identity.

The 0.9.1 Chibi and Last Light pairs carry one accepted, finite paragraph soundscape apiece, using the existing editable v6 / reading-data v5 support. No automatic retrofit is performed on an old reader ZIP. The Door Left Open and The Margin continue as reader-only works. [Release comparison](RELEASE-v0.9.1.md).
