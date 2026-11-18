# Public preview releases

A GitHub prerelease is not a stable release or a Pages rollout. Use an ordinary review branch from the verified public main; never import an unrelated private Git history or replace an existing tag. The [iteration history](ITERATION-HISTORY.md) is the public record of the intervening work.

## 0.9.1 local build: validate what the books actually do

Use a clean output directory, install the locked dependencies and rebuild the reader; do not replace any 0.9.0 file. Download the four original v0.3.3 Chibi/Last Light project/reader ZIPs from the [historical public release](https://github.com/Ethereal-Space-one/taleprism/releases/tag/v0.3.3). The exact two accepted sounds regenerate locally; private projects or audio downloads are not inputs.

```sh
OUT="$PWD/.release/v0.9.1"
uv sync --project backend --frozen
npm --prefix frontend ci && npm --prefix frontend run build
npm --prefix tools/webgal-verify ci --omit=dev
uv run --project backend python tools/build_release.py --public-inputs /path/to/v0.3.3-assets --output "$OUT"
```

On the reviewed commit, run the book-specific gate **before** finalizing checksums:

```sh
uv run --project backend python tools/check_edition_semantics.py --output "$OUT" --chromium /path/to/chromium --report "$OUT/edition-acceptance.json"
uv run --project backend python tools/check_reading_upgrade.py --output "$OUT" --previous /path/to/v0.9.0-readers --chromium /path/to/chromium
uv run --project backend python tools/finalize_release.py --output "$OUT"
```

Set `OUT` to the candidate asset directory. The gate compares four readers to the edition contract, then imports the two editable backups into fresh stores and checks their normal, unpatched reader exports. Browser checks and file checks answer different questions: a digest identifies bytes; it cannot tell you that a particular quote has the intended audible cue or that a prose description and reveal survived restoration. A static-only run is not a browser pass. Keep acceptance reports as build evidence, not as story assets. See [per-book criteria](VALIDATION-v0.9.1.md).

The live site was separately updated to the published 0.9.1 Chibi reader; a local rebuild never changes the site or existing release downloads. A future Pages change would be a separate, explicitly authorized operation: stage the selected Chibi reader, verify the candidate's per-book contract and every served file, retain the exact previously deployed archive for rollback, and compare live bytes after the approved switch. Do not treat passing local tests, a tag, or a Release as deployment authorization.

## Rebuild v0.9.0

Use the historical `v0.9.0` checkout and its own tools for these steps, not the current builder.

1. Install the locked Python and frontend/QA dependencies, run `npm --prefix frontend run build`, and compare `frontend/dist/reader/runtime-checksums.json` to both reader assets. Keep provider credentials unset. The WebGAL legacy integration tests also require its separately pinned engine.
2. Download the two reader/project pairs from the [v0.3.3 prerelease](https://github.com/Ethereal-Space-one/taleprism/releases/tag/v0.3.3). Place all four, with their original filenames, into a separate folder. The build verifies their digests before use, reimports the editable backups into empty stores, and verifies source, media and work identities. The earlier deployed Pages archive is not a release input.
3. Run `uv run --project backend python tools/build_release.py --public-inputs PATH --output .release/v0.9.0`. The two additional original examples are built as reader-only editions from the public inputs in `examples/encounters`. No authoring backups exist in their public outputs. The starter is a separate, explicitly allowlisted selection. The source inventory excludes build/cache data.
4. Review and pin the two curated catalog entries using `python tools/update_release_catalog.py .release/v0.9.0/release-manifest.json`; update the verify-first last-light pin in `guided_sample.py` to the same released project digest. Review the index and run `python tools/release_files.py --refresh` and `--check`. Commit all reviewed source and docs before the final source/starter build. Reuse an already verified local four-pair set with `--reuse-verified-pairs` only within the same trusted build.
5. `uv run --project backend python tools/check_public_preview.py --output .release/v0.9.0 [--chromium /path/to/chrome]` tests actual extracted book files, not mock DOM. Run the public backend, reader, formatting, prompt consistency, and source-inventory checks. Record limits in [validation](VALIDATION-v0.9.0.md).
6. Verify the final tag commit and tree. Run `uv run --project backend python tools/finalize_release.py --output .release/v0.9.0` from that exact clean commit. It verifies the frozen eight ZIPs and emits the manifest and SHA256SUMS. At the release upload exactly those ten assets, not build sidecars, input ZIPs or diagnostic reports. Verify the actual uploaded downloads against SHA256SUMS before marking it a prerelease. Never promote it as Latest or deploy Pages as a side effect.
