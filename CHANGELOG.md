# Changelog

## Unreleased — Reliability fixes

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
