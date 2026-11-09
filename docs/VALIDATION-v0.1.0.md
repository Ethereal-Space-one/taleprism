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
