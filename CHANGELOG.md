# Changelog

## 0.9.5 · Clearer project handoff

- Show which private still/motion judgments can travel separately and how many current placements need a new reveal-timing review after restoration. The reader and project package rules are unchanged.
- Guide authors who choose a Reader ZIP to the editable backup or the enclosed Project.zip, without weakening archive validation.
- Keep manually started sound playing when automatic effects are toggled in newly exported readers. Existing work bundles and Pages are not replaced by this source release.

## 0.9.4 · Let the story reveal itself

- Add a separate author check for what each placed image and its reader-facing words reveal at that point in the source. It is a human editorial decision, not a pass granted by matching a quotation or by a model.
- Keep draft previews, Reader downloads and editable backups available during review. Only formal Reader sign-off requires current per-image decisions, and their private reasoning does not travel with the book.
- In new Reader exports, the gallery starts with art at or before the current reading position. Seeing future illustrations or titles is a deliberate action for that visit. When an image is reused, the expanded view uses the selected placement’s own title and description.
- Harden UTF-8 source anchors across short lines, repeat passages and supplementary characters. Save soundscape intent in the workbench while keeping unaccepted cues out of exported readers.
- Validate the four current downloads independently of the frozen historical books and their contents; the existing online reader stays unchanged. [Release notes](docs/RELEASE-v0.9.4.md).

## 0.9.3 · A simpler download, from your novel or ours

- Put the Agent starter first, with a copyable first request and separate paths for folder-based and upload-only tools.
- Bundle Chibi and Last Light as one ZIP per work: open `Reader/index.html` to read or import the included `Project.zip` to edit.
- The standalone reader bytes, editable project archives, workbench runtime, older release downloads, and public Pages deployment do not change. This is a distribution preview. [Download guide](docs/DOWNLOADS.md) · [Release notes](docs/RELEASE-v0.9.3.md).

## 0.9.2 · An editorial decision for every placed illustration

- The workbench pairs each actual illustration with the text available at its place in the story. Formal sign-off requires a reasoned decision: keep still, propose supported motion, or defer an effect the tools cannot make. Draft exports remain available; a proposal never turns on animation.
- The four public books account for 17 plates: 12 deliberately still, two deferred and three already animated. Rebuilding all four reader ZIPs and both editable ZIPs preserves the bytes of 0.9.1. The authoring source and prompt starter change, not the books, their graphs, artwork or playback.
- For the editable books, an author can import the matching worksheet into an exact restoration with explicit consent. Private author notes are separate from reader and project exports. [Release notes / 中文说明](docs/RELEASE-v0.9.2.md) · [Checks and limits](docs/VALIDATION-v0.9.2.md).

## 0.9.1 · Published on GitHub

- Restore one source-bound, 12-second wind soundscape to Chibi (paragraph 12) and one 12-second rain soundscape to Last Light (paragraph 2). No dialogue, narration, score or changes to the other paragraphs. Existing shore and station picture motion are not new effects.
- Keep all twelve curated Chibi image descriptions and the two reveal delays when an author imports the example project and exports their own reader. The 0.9.0 distributed reader had those decisions; the ordinary editable-project round trip lost them. A copy remains its own project, not the public book.
- Add a book-specific handoff check: four delivered reading ZIPs and the actual unpatched exports of the two editable copies. A checksum alone cannot tell whether the right sound is at the right line. [Release notes](docs/RELEASE-v0.9.1.md) · [Verification](docs/VALIDATION-v0.9.1.md).

## 0.9.0 · Public preview (not stable)

- Read at your pace: finite soundscapes, reviewed local image motion and exact-text echo folds arrive at their source passage. Cover and quiet reading stay quiet; pause, mute and reduced motion remain independent.
- Authors can finish without requesting AI. Optionally review evidence-bound sound, picture and presentation proposals separately; unaccepted ideas do not travel to readers.
- Two original, reader-only examples demonstrate these cues; Chibi and Last Light remain the editable public examples. Release downloads and the existing Pages deployment are independent.
- The untagged 0.4.0, 0.5.0, 0.6.0, 0.6.1, 0.7.0 and 0.8.0 engineering iterations and the 0.9 reader changes are recorded in [Iteration history](docs/ITERATION-HISTORY.md). [Release guide](docs/RELEASE-v0.9.0.md) · [Validation scope](docs/VALIDATION-v0.9.0.md).

## 0.3.3 — Public Preview

- Review already reached chapter art without opening future plates or losing the current reading position.
- Add opt-in, evidence-bound environmental motion with finite rendering, static fallbacks and lifecycle cleanup. Keep human Prompt handoff guidance separate from the hand-written renderer.
- Bind Last Light rain to the audited normalized exported PNG; effects are visual overlays, not a per-drop physical simulation.
- Preserve prompt-library 0.2.1, editable-project format v2, canonical source text, Chibi artwork and existing online reading identity.

## 0.3.2 — Public Preview

- Add a one-click, loopback-only macOS launcher to standalone reader packages.
- Warn before revealing future titles and art in the complete Chibi gallery while preserving intentional full-chapter viewing.
- Update the independent prompt library to 0.2.1: source-bound reader intent, reference purpose, and separate visual and reader checks.
- Preserve canonical text, approved example artwork, project format v2 and existing online reader storage identity.

## 0.3.1 — Public Preview

- For the reviewed Chibi edition, keep future chapter titles and battle stages out of the default directory and map views; readers can deliberately reveal the full views.
- Accept simplified and traditional Chinese in reader search while preserving original source text and exact-match access.
- Fit an entire illustration when opening the reader's image viewer; allow panning only after explicit enlargement.
- Keep the Chibi wind and fire verse introductions with their poems, without changing source evidence or artwork.
- For Chibi, distinguish in-context image viewing from deliberate whole-chapter browsing, and describe image composition separately from narrative interpretation.
- Keep a maker-side record for the current Chibi image revisions and explicitly review cross-shot fleet continuity.

## 0.3.0 — Public Preview

- Add evidence-bound Chibi faction, relationship, phase and chapter-causality views that reveal only material already read and roll back on backward navigation.
- Harden reader image retry, audio cleanup, position restore, launcher workspace/process recovery and interrupted/repeated interactions.
- Add guided Last Light editing copies, portable project backup/restore notices and revision-bound shot prompt/image exchange.
- Support manual external-AI character/dialogue task exchange without sending content automatically, and report explicit WebGAL export losses.
- Rebuild and separately pin both public editable projects and standalone readers; retain prompt-library 0.2.0, project-format v2 and existing storage keys. Preserve v0.2.0 tags and attachments.

## 0.2.0

- Publish Chibi as a reproducible editable project with twelve source-bound shots and an updated online reader; keep Last Light as the short-story tutorial.
- Select identity-only references separately from display portraits and explicitly select reusable images.
- Resolve repeated dialogue through stable source anchors before creating projects.
- Remove optional Chibi-file dependencies from generic workflows, identify the correct running workspace and display the configured AI service.
- Use a reviewed public-source inventory and explicit per-example project/reader release pins.
- Restore editable projects with unresolved character/image review states while retaining source, reference and media integrity checks; show repair notices after import.
- Validate persisted cloud voice profiles separately from API requests so saved model metadata survives project migration.
- Add explicit failed/revoked continuity checks, invalidate dependent shots, and bind passing checks to source, image and character-reference snapshots. Legacy checks without this evidence remain readable and require reinspection.
- Verify every recipe input before replaying inspection records, including the original text and character portraits.
- Revoke affected audio acceptance when dialogue speakers change, preserving media and unchanged portable audio.
- Guard applied plan illustrations during reader delivery and export, including changes made during packaging. Previously completed artifacts remain available.

## Online showcase update — 2026-11-09

- Chibi becomes the public reading entry and repository cover: 12 scene illustrations, eight principal characters, nine portraits and three historical map stages.
- Last Light remains the short-story tutorial with its source, reference images, continuity exercises and existing downloads.
- Add a separately checksummed Chibi reader attachment; preserve the original v0.1.0 tag and released files. Pages selects its pinned example through `examples/site.json`.

## 0.1.0 — Public Preview

First public Taleprism trial, based on the earlier local Storygal project.

- Eight portable prompts for source evidence, acting, shot planning, scene/prop state, first images, continuation, review and repair. Workbench and standalone documents share versioned rules.
- Original Last Light tutorial in Chinese and English, with actual references, fixed-camera continuity records and documented bench/basket repairs.
- Local workbench for source-preserving review, character assets, scene direction, optional speech, continuity checks and reader export.
- Editable projects keep v1/v2 compatibility; upstream changes invalidate dependent checks. Existing local data and browser progress keys stay unchanged.
- Public branding becomes Taleprism. Missing optional content packages explain how to download and import them.
- Separate prompt starter, editable project and static reader downloads, with integrity manifests. Public example excludes macOS demonstration audio.

Known limits: Chinese workbench UI; no native Windows launcher, whole-book automation or proven arbitrary-view consistency. OpenAI voice is prepared, not live-validated. External-user onboarding and final creator art review are still pending. See the versioned validation report for actual checks.
