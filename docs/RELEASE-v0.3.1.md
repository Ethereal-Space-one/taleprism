# Taleprism v0.3.1 Public Preview

A focused reader and Chibi editorial update relative to the public v0.3.0 preview. Existing source text, artwork, project formats and reading-state identifiers are preserved.

## Changes

- Chibi's directory and map hide future chapter titles and battle stages by default. Full views remain an explicit reader choice, and first-reading image browsing stays within reached pages unless the reader deliberately chooses the whole chapter.
- Reader search accepts Simplified and Traditional Chinese, with original text and exact-match access preserved. Redistributed OpenCC data includes its required notices.
- Opening an illustration fits the whole image; panning begins only after deliberate enlargement.
- Chibi wind/fire introductions remain beside their poems. Display placement is separate from source anchors, and image composition is distinguished from narrative interpretation.
- Maker-side Chibi image lineage records historical prompts and revisions without inventing missing evidence. A paired-shot review explicitly identifies the current fire-ship flag-color inconsistency.

## Downloads

Six ZIPs follow the v0.3.0 release layout: Chibi editable project and standalone reader, Last Light editable project and standalone reader, prompt starter, and curated application source. `release-manifest.json` binds the exact bytes to one commit; verify them with `SHA256SUMS`. Import project ZIPs into the workbench. Extract and verify readers, then serve them over HTTP or static hosting.

- [Install the v0.3.1 workbench](https://github.com/Ethereal-Space-one/taleprism/tree/v0.3.1#readme)
- [Read Chibi online](https://ethereal-space-one.github.io/taleprism/), which changes only through a separately verified deployment
- [Validation record](https://github.com/Ethereal-Space-one/taleprism/blob/v0.3.1/docs/VALIDATION-v0.3.1.md)

## Compatibility and known limits

Prompt-library 0.2.0, project-format v2, the Chibi 0.2 reconstruction recipe/review versions, source/media bytes and persisted IDs remain unchanged. Existing tags and release attachments are not replaced.

The Huang Gai departure → Cao Cao observation → fire panorama flag-color gate remains **`needs_revision`**. Unifying the flag color is a proposal for a future correction, not an applied repair. Existing individual-image assistant checks do not pass this supplemental gate. Creator final art approval remains pending.

Public examples have no system demonstration audio. Independent external-user onboarding, live OpenAI synthesis and arbitrary-view consistency remain unverified. The UI is Chinese; native Windows startup remains unsupported. Local checks do not establish remote CI, uploaded-asset integrity or a Pages deployment.
