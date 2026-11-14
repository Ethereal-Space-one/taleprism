# Taleprism v0.3.1 candidate validation

Prepared on Linux in an isolated checkout of the accepted reader/narrative changes. This record describes local release preparation, not an uploaded GitHub Release or deployed Pages site. Existing locked Python/frontend dependencies and the pinned WebGAL 4.6.5 engine are reused; temporary build/test data is separate from the system temporary filesystem. No paid AI service, image generation or private project is used.

## Local candidate checks

The application and matching package/lock metadata advance to 0.3.1. Prompt-library 0.2.0, project-format v2, the Chibi 0.2 reconstruction recipe/review versions and persisted source/work/illustration IDs remain independent. Historical release/validation documents are unchanged.

| Check | Observed result |
| --- | --- |
| Runtime and metadata | Python 3.12.14 / Node.js 24.22.1; package/lock/API/footer metadata agree on 0.3.1. Offline `uv lock --check --offline` passed. |
| Frontend | TypeScript/Vite production build, reader Prettier check and all eight reader regression groups passed, including disclosure, Simplified/Traditional search, poem-safe placement and image browsing. |
| Backend and source | Ruff, generated prompt/schema check and the explicit 282-file public-source inventory passed. The settled-catalog CI-equivalent public backend aggregate passed: 557 tests, 10 deselected for the same optional historical fixtures as CI. Launcher coverage passed: 31 tests. |
| Guided tutorial | All 18 guided-sample tests passed with the exact frozen Last Light project, including verified-cache offline import, code/catalog pin agreement and fixed-origin/download boundaries. |
| Public example rebuild | Both editable-project/reader pairs rebuilt from public inputs only. The pinned public Chibi v0.1.0 reader hash, source and all 27 images, twelve production checks, clean project roundtrip and public work/illustration IDs were verified. Last Light retains three shots and eleven scene objects. Both examples omit system audio. |
| Frozen pins and inventories | Catalog pins identify each example and kind separately; guided Last Light uses the frozen 0.3.1 project. Pages preparation verified the local archives and every contained file: 83 Chibi payload files and 25 Last Light payload files. Source/starter finalization verifies six ZIPs against the committed source and records SHA-256 checksums. |
| Comparison with public 0.3.0 | Chibi project identity, source blocks, media metadata and all 27 media bytes are identical; Last Light source and six media bytes are unchanged. Last Light rebuilds receive their own independent project identity. Historical release/validation documents are unchanged. |
| Maker provenance | Twelve current Chibi assets traced; the supplemental paired-shot gate remains `needs_revision`, and `flag_correction_applied` is false. |
| Browser acceptance | Not completed locally. Chromium aborts before opening the candidate because process-singleton socket creation is not permitted. No final frozen-reader desktop/mobile browser pass is claimed. |

A first aggregate overlapped the catalog pin update and its already-imported guided-sample module saw stale constants. After settling the pins, the entire aggregate was rerun and passed as recorded above. The known Starlette/httpx deprecation warning is not a test failure.

## Known unresolved review

The maker-side Chibi paired-shot review remains `needs_revision` for the fire-ship flag-color difference across Huang Gai departure, Cao Cao observation and the fire panorama. The proposed canonical color is not applied. Historical prompts, original source, all 27 images and individual-image assistant checks remain intact; creator final art review is pending.

## Publication gates

- Require actual Ubuntu/macOS checks on the exact final candidate commit.
- Create only the new v0.3.1 tag and release; preserve all older releases, tags and attachments.
- Download and checksum the uploaded six ZIPs, manifest and checksum file before publication.
- Treat Pages deployment as separate work and verify any deployed pin, source/media hashes, reading progress, desktop/mobile behavior, console and links.

A fresh dependency installation, independent external-user onboarding, live OpenAI synthesis, native Windows startup and arbitrary-view consistency are not established by local reuse of dependencies.
