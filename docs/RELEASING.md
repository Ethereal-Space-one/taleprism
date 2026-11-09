# Release procedure

1. Freeze scope, update versioned prompts and docs, run the checks in CONTRIBUTING. Regenerate prompts/schemas and verify they are current.
2. Build the frontend, then `uv run --project backend python tools/build_release.py --output .release/v0.1.0`. It rebuilds Last Light from the inspected recipe through the API in temporary storage, includes no system audio, round-trips the project, verifies the independent reader and creates the prompt starter.
3. Review `tools/release_files.py`'s public inventory. `python3 tools/package_source.py` packages the same curated source selection; local data, credentials, dependency directories, old handoff ZIPs and large historical image packs stay outside the public source. Canonical Last Light images remain in source to avoid first-release bootstrap dependencies.
4. Test the curated archive in a fresh directory with fresh application data. Check the reader under a project subpath on desktop and mobile; no workbench API requests are allowed. Record actual results in the versioned validation report, including limitations.
5. Create the repository or use the maintainer's chosen remote. A public repository exposes its source before a Release is published. Run GitHub checks for the candidate. Keep repository history free of runtime data; use the explicit source inventory for the initial commit.
6. Freeze the final passing commit and create tag `v0.1.0`. Set the release manifest's `commit` to that SHA. Create a draft Pre-release and attach the three ZIPs plus manifest and checksums. Download the actual attachments and verify their hashes. Do not rebuild after recording their checksums.
7. Publish the Pre-release. Enable Pages using GitHub Actions. The Pages job downloads the exact reader attachment and verifies its committed catalog checksum before deployment. Check the published URL and all README download links from a clean browser.
8. Preserve published files. Fix substantive issues in a patch release instead of silently replacing archives. Capture independent-user feedback; never claim art approval or external validation based only on automated tests.

The first release must not depend on downloading itself to build its assets. Core CI uses source fixtures and synthetic sound; local historical full-pack tests remain optional. The post-release Pages job may consume the published reader because its exact checksum is already committed in `samples/content-packs/catalog.json`.

No publication credentials belong in files. CI uses GitHub's scoped job token; local maintainers use their GitHub login. Normal installation and tests never call paid AI services.

## Updating the featured online example

`examples/site.json` selects the public showcase (currently `chibi`). `tools/prepare_pages.py` reads that entry’s pinned reader from `samples/content-packs/catalog.json`; `--example last-light` explicitly selects the tutorial reader. Manual Pages runs check out the selected branch, then verify the exact release asset and its internal inventory.

For the reviewed historical Chibi source bundle, build the isolated public copy with `uv run --project backend python tools/build_chibi_demo.py`. This requires the maintainer’s matching local bundle; ordinary installation and CI do not require that private working copy. Inspect the actual images first and retain hash-bound review notes. Add a uniquely named reader and integrity files to the release, preserving existing attachments and tags; commit its catalog pin and documentation, run checks, and then trigger Pages with `gh workflow run pages.yml --ref main`. Check the deployed URL on desktop and mobile. Changes to application behavior still require a normal versioned release.
