# Taleprism v0.3.0 candidate validation

Prepared on Linux with Python 3.12.14, Node.js 24.22.1 and the existing locked dependencies in an isolated public-source checkout. This record applies to a local candidate, not an uploaded release or a deployed website. All three original lockfiles matched the reused dependencies before the application and matching root lock metadata were advanced to 0.3.0. Build and test temporary data use a separate workspace rather than the capacity-limited system temporary filesystem.

## Observed checks at source freeze

| Check | Observed result |
| --- | --- |
| Application metadata | Backend project and lock, API/app metadata, frontend package and lock, verification-tools package and lock, and visible footer agree on 0.3.0. Offline lock validation passed. |
| Frontend | TypeScript/Vite build and reader Prettier check passed. Reader model, recovery, audio lifecycle and edition-bound story-graph checks passed. |
| Backend and release tools | Ruff, generated prompt/schema verification and the explicit public-source inventory passed. Launcher and new release-boundary tests passed: 38 tests. A final public backend aggregate is run with the same optional historical-fixture omissions as CI; its exact final result must be checked in the candidate evidence and GitHub Actions before publication. |
| Public example rebuild | Both editable-project/reader pairs were rebuilt from public inputs only. The Chibi builder verified the pinned v0.1.0 input, unchanged source and all 27 image bytes, twelve production checks, clean import/re-export and preserved public/progress IDs. Last Light retained three shots and eleven scene objects. Both examples omit system demonstration audio. |
| Frozen pins | Catalog project and reader pins identify each example separately. The guided Last Light allowlist uses the frozen 0.3.0 project filename, URL and SHA-256. Its fixed-origin and content-integrity rules are unchanged. |
| Pages preparation | The local candidate Chibi reader passed the same outer checksum, per-file inventory and safe extraction checks used by Pages preparation. Lower-case `/taleprism/` references are retained. |
| Browser acceptance | Not completed in this execution environment. Chromium aborts before opening the candidate because process-singleton socket creation is not permitted. No screenshots or desktop/mobile acceptance pass are claimed. |

The Chibi 0.2 reconstruction recipe and visual-review bytes were not edited or relabelled. The builder now validates that supported reviewed content version independently of the application version and rejects output under existing 0.1/0.2 release paths. Regression tests cover these boundaries. Prompt-library 0.2.0, project-format v2 and persisted storage keys remain independent.

## Publication gates not performed locally

- Push the exact candidate commit and require its actual Ubuntu/macOS GitHub Actions checks to pass.
- Create a new v0.3.0 tag and draft Pre-release; preserve v0.2.0 and all its attachments.
- Upload the six ZIPs, manifest and checksums, then download and verify the actual attachments before publishing.
- Deploy only the committed Chibi catalog pin and verify the real Pages URL, desktop/mobile reading, images, graphs, progress migration, console and README links. The existing lower-case `/taleprism/` subpath is preserved pending a separate repository-name decision.

Creator final art review, live OpenAI synthesis, independent external-user onboarding and native Windows startup are not established by these local checks. No private project, paid model, image-generation service or GitHub mutation is used in local reconstruction. A fresh dependency installation was not performed here; reused dependencies are not a clean-install acceptance result.
