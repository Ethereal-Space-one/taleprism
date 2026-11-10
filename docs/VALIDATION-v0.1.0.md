# Taleprism v0.1.0 validation

Recorded 2026-11-09. These checks cover software behavior and the supplied example. They do not grant creator art approval or prove arbitrary-view image consistency.

| Check | Observed result |
| --- | --- |
| Full local regression suite with retained historical assets | 107 passed on macOS; one upstream Starlette/httpx test-client deprecation warning |
| Fresh curated source, new Python environment and fresh npm install | Installation and frontend build passed without developer data or packed historical samples |
| Source-only core suite | 41 passed, 3 explicitly skipped: optional WebGAL integration and two historical full-pack imports |
| Source-only review suite | 7 passed; 2 optional export cases excluded from this subset and covered by the full local suite |
| Shared prompt/schema exports | Eight templates match runtime rules; schema references resolve |
| New fictional archive-room worksheet | Generic source/character/prop-state flow passes without model calls; no new images were generated |
| Synthetic audio portability | Test-generated sound migrates and exports without an installed system voice |
| Public Last Light build | Rebuilt through APIs in temporary storage; 3 shots, 11 objects; original bytes preserved; no system audio |
| Editable project migration | Import and independent reader re-export passed; assistant checks retained, final creator review not inherited |
| Browser: real Chrome on macOS | Workbench import, 1440px/375px layouts and source text equality passed; no page errors |
| Independent reader under `/taleprism/` | All three pictures load, desktop/mobile reading and reload work; no workbench API requests |
| Reader state/formatting checks | Navigation transitions, legacy browser records, Unicode anchors and literal search passed; reader formatting passed |
| Public source selection | Approximately 22 MB before compression; no runtime data, credentials, personal absolute paths or large historical packs in the curated inventory |
| Markdown links | Local Markdown targets resolve within the curated source inventory |

GitHub runs the source-only checks and public-asset build on both Ubuntu and macOS. Actual results for the tagged commit are linked from GitHub's checks; the downloadable `release-manifest.json` records the release commit and final workflow evidence. A configured workflow alone is not a pass. Linux automation does not imply a separate manual Linux browser/voice review. Native Windows startup is not supported.

The original images are unchanged. Their earlier assistant inspection and bench/basket repair notes remain in `samples/last-light/continuity-review.json` and `continuity-prompts-v2.json`, with exact hashes. The intermediate defective candidates were not archived in the public kit; v1/v2 images demonstrate the broader workflow iteration, not those intermediate repairs.

Minor local brushwork/contour drift remains. Other image models, reverse shots, live OpenAI voice quality, independent external-user onboarding and final creator art review are **not validated** by this report. The workbench UI is Chinese. Public examples omit macOS system-generated demonstration audio.

## Chibi online showcase update · 2026-11-09

The original tagged release and its attachments remain unchanged. These additional checks apply to the separately added Chibi reader and current showcase configuration:

- Isolated export preserves all original novel bytes and the original local bundle hash. The package contains 12 illustrations, eight characters, nine portraits, 55 presentations and three map phases; no system audio is included.
- Outer ZIP checksum and all 57 delivered files pass the Pages verifier and the reader's standalone verifier.
- Chrome on macOS at 1440px and 375px: all 12 scene images and nine portraits decode, rendered source matches the novel, all three map phases switch, reload succeeds and there is no horizontal page overflow. No JavaScript errors, failed resource responses or workbench API requests occurred.
- Four release tests pass, including featured-example selection, explicit Last Light selection and rejecting an unknown example. Updating the Last Light catalog retains the pinned Chibi reader; the existing Last Light download checksums remain identical.
- The desktop cover and mobile reading/map screenshots were visually inspected. Two historical revised illustrations have separate hash-bound assistant inspection notes in `examples/chibi/demo-review.json`; creator final art approval remains pending.

The public deployment is verified again after Pages completes; the workflow run and browser result are recorded in the maintainer's local publication record. CI automation is not claimed as another manual platform review.

## Unreleased reliability fixes · 2026-11-10

This section records local fixes for audit items 1–6, developed on `codex/p1-reliability-fixes`. Four implementation agents worked on separate modules, followed by an independent integration review. It does not replace the tagged v0.1.0 validation, release attachments or deployed Chibi showcase.

| Scope | Verified behavior |
| --- | --- |
| Editable recovery | Unconfirmed characters and rejected referenced assets retain their saved composition and approval state; import reports repair needs. Invalid ownership, missing references and corrupt files remain rejected. |
| Cloud voice metadata | Persisted OpenAI profile/model and take metadata migrate without a real cloud request; unsupported fields and inconsistent metadata fail validation. |
| Continuity decisions | Explicit pass/fail/revoke decisions preserve reasons; upstream changes revoke dependent checks. Old checks without dependency evidence require reinspection. |
| Actual references | Source, image and character-reference hashes bind checks. Switching A→B→A does not revive a passed check; unrelated characters do not invalidate it. Valid merge chains restore historical references as non-passing; missing/cyclic chains and unrelated ownership are rejected. |
| Recipe replay | Original source, portraits, scene images and recipe bytes are checked before creating a project. Missing, extra or changed dependencies stop replay; uploads use the validated bytes. |
| Speaker identity | Reassignment and character merging invalidate affected audio acceptance, including imported audio with identical voice settings. Media and unaffected accepted segments survive migration. |
| Export and final review | Applied plan illustrations cannot bypass withdrawn checks. Mid-export changes remove unfinished output; a concurrent revoke before final-review commit returns 409 without inserting or replacing review records. Existing completed ZIPs remain downloadable. |

Observed verification:

- **244 passed** in the full local backend regression suite, including retained historical assets. One existing upstream Starlette/httpx test-client deprecation warning remains.
- **187 passed, 3 skipped** in the CI-selected suite extracted from the curated source archive; **7 passed, 2 deselected** in its review subset. The three skips are the optional WebGAL engine test and two historical full-pack imports; those ran in the full local suite. This check reused installed Python dependencies and the newly built frontend, so it is not a new dependency-installation test.
- Frontend TypeScript/production build, reader state checks, formatting of the changed components, Python lint, generated prompt/schema synchronization and diff checks passed.
- Fresh local sample construction, editable import and reader re-export passed in isolated storage, including a construction run from the curated source archive. Original source bytes, three illustrations, 11 scene objects, portable paths and file inventories were verified. No system voice audio was included.
- Real Chrome on macOS: importing a checked example, explicit failure/revocation, blocked delivery, restoring an unresolved project with warnings, rechecking each frame and exporting again passed. At 1440px/375px there was no horizontal overflow. Screenshots were visually inspected; rejected/revoked states have distinct indicators.
- The resulting standalone reader loads all three illustrations at mobile width, displays the unchanged text and makes no workbench API requests. No JavaScript page errors occurred; package verification passed.
- Synthetic workflow checks performed by tests remain confined to temporary projects and do not constitute creator art approval. The canonical artwork is unchanged; the Last Light dependency-record upgrade preserves its original reviewer, date and notes and explicitly records the hash-only upgrade.

The new regression cases are included in the Ubuntu/macOS workflow configuration. No remote CI execution, publication, live OpenAI synthesis or new art inspection is claimed for this local patch. Browser reproduction is available in `tools/webgal-verify/reliability-check.cjs`; run it against isolated storage and a fresh local build, never a working project.
