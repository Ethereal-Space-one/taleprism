# Taleprism v0.2.0 Public Preview

Taleprism combines unchanged fiction with character direction, illustrations, scene continuity and optional voices. This release makes unfinished projects recoverable and makes the Chibi showcase available as an editable, reproducible example.

## Start here

- [直接阅读《赤壁》 / Read Chibi online](https://ethereal-space-one.github.io/taleprism/).
- [安装制作台并导入工程 / Install the workbench and import a project](https://github.com/Ethereal-Space-one/taleprism/tree/v0.2.0#readme).
- [使用八个提示词模板 / Use the eight prompt templates](https://github.com/Ethereal-Space-one/taleprism/tree/v0.2.0/prompts).

## Changes

- Restore unfinished projects without discarding editorial choices or weakening source and file integrity checks. OpenAI voice model metadata survives migration.
- Record explicit pass, fail and revoke decisions. Checks bind their source, image and character references; dependent checks require renewal after changes. Export and final-review transactions reject stale production state.
- Select identity-only references separately from display portraits and identify the exact image to reuse.
- Resolve repeated dialogue by source anchors and validate reconstruction inputs before creating a project.
- Use the workbench without optional Chibi files, identify the correct running workspace and show the configured AI service accurately.
- Package only explicitly listed public files. Keep the Chibi and Last Light project/reader downloads separately pinned by checksum.
- Offer Chibi as both an editable project and the featured standalone online reader, with a source-bound twelve-shot plan. Last Light remains the three-shot tutorial.

## Downloads

The release contains six ZIPs. `SHA256SUMS` and `release-manifest.json` give the checksums and source commit. Import project ZIPs into the workbench and serve extracted reader ZIPs over local HTTP or static hosting. See the [quick start](https://github.com/Ethereal-Space-one/taleprism/blob/v0.2.0/docs/%E5%BF%AB%E9%80%9F%E4%B8%8A%E6%89%8B.md) and [Chibi reconstruction guide](https://github.com/Ethereal-Space-one/taleprism/blob/v0.2.0/examples/chibi/README.md).

| ZIP suffix | Contents |
| --- | --- |
| `chibi-project.zip` | Editable Chibi project with 12 shots and 9 production scenes |
| `chibi-reader.zip` | Standalone showcase with 12 illustrations, 9 portraits and 3 map phases |
| `last-light-project.zip` | Editable three-shot tutorial project |
| `last-light-reader.zip` | Standalone reading edition of the tutorial |
| `prompt-starter.zip` | Eight templates, schemas, tutorial text and reference images |
| `source.zip` | Curated workbench source and reproducible examples |

## Compatibility and boundaries

Existing v1/v2 projects remain importable. Old checks without dependency evidence need reinspection; imported checks do not grant final creator approval. New fields may require the 0.2 workbench. Existing 0.1 attachments and original local projects remain available.

Public examples contain no system-generated demonstration audio. Live OpenAI synthesis, arbitrary-view image consistency and independent external-user onboarding are not established by automated regression results. The UI remains Chinese; native Windows startup is not implemented. Reading interaction items 9–11 are scheduled for 0.2.1 unless they block this release's acceptance.

See the [validation record](https://github.com/Ethereal-Space-one/taleprism/blob/v0.2.0/docs/VALIDATION-v0.2.0.md) for the checks completed for this release.
