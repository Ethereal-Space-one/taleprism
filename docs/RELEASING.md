# Taleprism releases

A GitHub prerelease is not a stable release or a Pages rollout. Use an ordinary review branch from the verified public main; never import an unrelated private Git history or replace an existing tag. The [iteration history](ITERATION-HISTORY.md) is the public record of the intervening work.

## Acceptance for an authoring-flow change

- Start as a new reader or author from the exact candidate README, Agent starter and work ZIP, not from an existing local workspace. Compare the linked revision and verify the packaged `Reader/index.html` and inner `Project.zip` separately. A draft that opens is not a signed edition.
- Replay a short source in which the same correct quote can anchor either a faithful image or one containing a later reveal. Use actual images and inspect the Reader placement and public copy. Draft export and project restore should work before approval; a missing, disputed, or stale timing decision must block formal sign-off. Check that private notes do not appear in any archive member. Change the placed image, paragraph or reader-facing description to make sure confirmation cannot follow the wrong artifact.
- If claiming phone support, test a cold offline open from a fully extracted work ZIP in iPhone Files separately from Safari over HTTPS. Record the opener and whether touch, text, art, and media work; a desktop narrow viewport does not count. For automatic sound, use two distinct accepted cues separated by enough text to scroll naturally. After any single needed activation, the second cue must start without a second tap. Check mute, quiet reading, and no replay on search jump separately. Log untested surfaces as untested.

## 0.9.3 distribution layout: one download per work

This is the layout used by the published v0.9.3 preview. To reproduce its
historical attachments, use the exact v0.9.3 source. The same four-download
layout is used by v0.9.4: lead with the author starter, group the two complete
works, and show the workbench last, without replacing older downloads or
deploying Pages.

| What the visitor wants | New release attachment |
| --- | --- |
| Bring my novel to an AI agent | `taleprism-agent-starter.zip` |
| Read or edit Chibi | `taleprism-chibi-work.zip` |
| Read or edit Last Light | `taleprism-last-light-work.zip` |
| Install the local workbench | `taleprism-workbench-source.zip` |

Each work ZIP has a bilingual `README.md`, the expanded `Reader/` (open
`Reader/index.html`), and an intact `Project.zip` (import into the workbench).
There is no extra reader ZIP to unpack. The work ZIP is not an import target.
The two [reader-only works](DOWNLOADS.md#仅试读--reader-only) stay in the works
index at their existing published URLs. Put `candidate-manifest.json` and
`SHA256SUMS` under a separate verification heading; GitHub adds its own
automatic source snapshots.

Obtain the four unchanged v0.9.2 Chibi and Last Light reader/project ZIPs from
the [published release](https://github.com/Ethereal-Space-one/taleprism/releases/tag/v0.9.2),
or the exact matching outputs of the historical builder below. Build in a
separate output directory; the bundler checks the fixed input digests. CI uses
Python 3.12 for both package tests and actual candidate builds on Ubuntu and macOS.

```sh
uv sync --project backend --frozen --python 3.12
uv run --project backend --frozen --python 3.12 python tools/build_distribution_candidate.py --inputs /path/to/v0.9.2-zips --output .release/distribution
(cd .release/distribution && shasum -a 256 -c SHA256SUMS)
```

**What ordinary CI verifies.** New reader code is not an input for reconstructing a
historical work: a change to the current reader JavaScript would change the original
ZIP hash even when nothing in the novel changed. Both platforms build the four
current downloads using pinned historical inputs. The builder reopens each work
ZIP and checks its exact member set, reader file bytes, executable launcher modes,
work-specific guide and intact inner project against independent input pins. It also
reopens the starter and source archive, comparing all members to the current
starter selection or reviewed source inventory, including executable modes.
New editions must use new pins and an explicitly reviewed release; never update old
pins to make a development build pass.

Linux CI also uses `tools/check_edition_semantics.py --frozen-books /path/to/v0.9.2-zips`
with **all six** pinned book ZIPs (four readers, two projects). This exercises the
unchanged readers and imports the editable versions into the **current** workbench,
then opens its ordinary new exports. Those exports are checked against book intent
(source, art, anchors and sound), not against the frozen JavaScript hash.
A frozen-book compatibility receipt is not a release-finalization receipt. To
reproduce the historical eight-attachment build, use the historical source and
procedure below.

Before publishing a separately authorized release, verify the Linux and macOS
checks for its exact source commit. Validate the exact new downloads: extract
each work once, open the bundled reader offline, import only its `Project.zip`
into a fresh store, and verify original text, placed art and paragraph soundscape
in the default re-export. A structural or static check is not a browser pass.
Test the Agent starter from its own README and source setup from a clean directory.

The final `candidate-manifest.json` must identify the current application version,
exact tag commit and separate historical book-input tag. Compare it and
`SHA256SUMS` to the expected CI evidence. Attach the four ZIPs and those two
verification files to a draft for the **new** tag. Verify the uploaded downloads,
then publish with the authorized stability setting. Never overwrite a published
tag, replace old attachments or deploy Pages as a side effect.

## 0.9.2 local build: review every plate without changing the books

Use a clean output directory, install the locked dependencies and rebuild the reader; do not replace any 0.9.0 file. Download the four original v0.3.3 Chibi/Last Light project/reader ZIPs from the [historical public release](https://github.com/Ethereal-Space-one/taleprism/releases/tag/v0.3.3). The exact two accepted sounds regenerate locally; private projects or audio downloads are not inputs.

```sh
OUT="$PWD/.release/v0.9.2"
uv sync --project backend --frozen
npm --prefix frontend ci && npm --prefix frontend run build
npm --prefix tools/webgal-verify ci --omit=dev
uv run --project backend python tools/build_release.py --public-inputs /path/to/v0.3.3-assets --output "$OUT"
```

On the reviewed commit, run the book-specific gate **before** finalizing checksums:

```sh
uv run --project backend python tools/check_edition_semantics.py --output "$OUT" --chromium /path/to/chromium --report "$OUT/edition-acceptance.json"
uv run --project backend python tools/check_reading_upgrade.py --output "$OUT" --previous /path/to/v0.9.0-readers --chromium /path/to/chromium
TALEPRISM_CHROMIUM=/path/to/chromium node tools/webgal-verify/plate-screening-workbench.cjs
uv run --project backend python tools/check_plate_studies.py --output "$OUT" --chromium /path/to/chromium --report "$OUT/plate-screening-acceptance.json"
uv run --project backend python tools/finalize_release.py --output "$OUT"
```

For 0.9.2 the finalizer also requires the current catalog, every current worksheet, and the separate fresh-browser plate-screening receipt for the actual four reader ZIPs. Recheck this when an edition, image or anchor changes. This adds a build rule, not a replacement of a previously published tag.

Set `OUT` to the candidate asset directory. The gate compares four readers to the edition contract, then imports the two editable backups into fresh stores and checks their normal, unpatched reader exports. Browser checks and file checks answer different questions: a digest identifies bytes; it cannot tell you that a particular quote has the intended audible cue or that a prose description and reveal survived restoration. A static-only run is not a browser pass. Keep acceptance reports as build evidence, not as story assets. Review [0.9.2 checks and limits](VALIDATION-v0.9.2.md) and the [unchanged per-book criteria](VALIDATION-v0.9.1.md).

0.9.2 keeps the internal book edition at 0.9.1. All six book ZIP hashes must match the public 0.9.1 release; the name in the new download URL is not an edition migration. Source and prompt starter are new. Upload the eight frozen ZIPs plus the finalized manifest and SHA256SUMS, not the build receipts. Use the receipts from CI for the exact reviewed commit.

The live site was separately updated to the published 0.9.1 Chibi reader; a local rebuild never changes the site or existing release downloads. A future Pages change would be a separate, explicitly authorized operation: stage the selected Chibi reader, verify the candidate's per-book contract and every served file, retain the exact previously deployed archive for rollback, and compare live bytes after the approved switch. Do not treat passing local tests, a tag, or a Release as deployment authorization.

## Rebuild v0.9.0

Use the historical `v0.9.0` checkout and its own tools for these steps, not the current builder.

1. Install the locked Python and frontend/QA dependencies, run `npm --prefix frontend run build`, and compare `frontend/dist/reader/runtime-checksums.json` to both reader assets. Keep provider credentials unset. The WebGAL legacy integration tests also require its separately pinned engine.
2. Download the two reader/project pairs from the [v0.3.3 prerelease](https://github.com/Ethereal-Space-one/taleprism/releases/tag/v0.3.3). Place all four, with their original filenames, into a separate folder. The build verifies their digests before use, reimports the editable backups into empty stores, and verifies source, media and work identities. The earlier deployed Pages archive is not a release input.
3. Run `uv run --project backend python tools/build_release.py --public-inputs PATH --output .release/v0.9.0`. The two additional original examples are built as reader-only editions from the public inputs in `examples/encounters`. No authoring backups exist in their public outputs. The starter is a separate, explicitly allowlisted selection. The source inventory excludes build/cache data.
4. Review and pin the two curated catalog entries using `python tools/update_release_catalog.py .release/v0.9.0/release-manifest.json`; update the verify-first last-light pin in `guided_sample.py` to the same released project digest. Review the index and run `python tools/release_files.py --refresh` and `--check`. Commit all reviewed source and docs before the final source/starter build. Reuse an already verified local four-pair set with `--reuse-verified-pairs` only within the same trusted build.
5. `uv run --project backend python tools/check_public_preview.py --output .release/v0.9.0 [--chromium /path/to/chrome]` tests actual extracted book files, not mock DOM. Run the public backend, reader, formatting, prompt consistency, and source-inventory checks. Record limits in [validation](VALIDATION-v0.9.0.md).
6. Verify the final tag commit and tree. Run `uv run --project backend python tools/finalize_release.py --output .release/v0.9.0` from that exact clean commit. It verifies the frozen eight ZIPs and emits the manifest and SHA256SUMS. At the release upload exactly those ten assets, not build sidecars, input ZIPs or diagnostic reports. Verify the actual uploaded downloads against SHA256SUMS before marking it a prerelease. Never promote it as Latest or deploy Pages as a side effect.
