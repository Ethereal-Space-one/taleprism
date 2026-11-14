# Taleprism v0.3.0 Public Preview

This preview improves both sides of illustrated reading: recovering a reliable reading session and carrying an unfinished creative project forward without losing its source evidence.

## Start here

- [Read Chibi online](https://ethereal-space-one.github.io/taleprism/). The live site changes only after a separately verified deployment.
- [Install the workbench](https://github.com/Ethereal-Space-one/taleprism/tree/v0.3.0#readme).
- [Use the eight prompt templates](https://github.com/Ethereal-Space-one/taleprism/tree/v0.3.0/prompts), whose independent library version remains 0.2.0.

## Changes

- Chibi gains evidence-bound faction, relationship, stage and chapter-causality views. They reveal only information reached in the text; backward navigation hides later results again. The graphs do not infer relationships for unsupported texts.
- Reader image retry, interrupted audio, session recovery and source-bound reading positions receive dedicated regression coverage.
- Guided Last Light practice creates a separate editable copy from a fixed, checksummed public project. Existing projects remain untouched.
- Project backup/restore notices and revision-bound individual-shot task/image exchange make unfinished work easier to move and repair.
- Character/dialogue tasks can be downloaded for an external AI and validated on return. Taleprism does not upload the task or contact that AI; sharing the source is the user's choice.
- WebGAL export describes the reader features it will omit and requires an explicit, revision-bound simplification decision.

## Downloads

Six ZIPs are accompanied by `release-manifest.json` and `SHA256SUMS`. The manifest binds these frozen bytes to one source commit. Import `project.zip` files into the workbench. Extract and verify reader ZIPs, then serve them over local HTTP or static hosting.

| ZIP suffix | Contents |
| --- | --- |
| `chibi-project.zip` | Editable twelve-shot Chibi project with nine production scenes |
| `chibi-reader.zip` | Standalone Chibi reader, twelve illustrations, nine portraits and three map phases |
| `last-light-project.zip` | Editable three-shot tutorial project |
| `last-light-reader.zip` | Standalone tutorial reader |
| `prompt-starter.zip` | Eight templates, schemas, tutorial text and reference images |
| `source.zip` | Curated application source and public reference materials |

## Compatibility and limits

Existing project formats v1/v2, public source bytes, artwork and browser storage identifiers remain compatible. The Chibi reconstruction recipe and recorded visual review retain their 0.2 versions because their content has not changed. This release does not move the v0.2.0 tag or replace its attachments.

Public examples omit system demonstration audio. Creator final art approval, independent external-user onboarding, live OpenAI synthesis and arbitrary-view image consistency remain unverified. The interface is Chinese. Native Windows startup remains unsupported. Local candidate checks are not a claim that GitHub Actions, uploaded assets or a Pages deployment have passed.

See the [validation record](https://github.com/Ethereal-Space-one/taleprism/blob/v0.3.0/docs/VALIDATION-v0.3.0.md) for observed checks and outstanding publication gates.
