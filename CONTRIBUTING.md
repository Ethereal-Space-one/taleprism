# Contributing to Taleprism

Start with [README](README.md), [architecture](docs/ARCHITECTURE.md) and [compatibility](docs/COMPATIBILITY.md). Keep new novels in content/recipes; do not add character-name or source-sentence branches to generic code.

## Setup and checks

Install uv and Node.js 22.12+, then run `./start.sh`. For development, run `uv run --project backend uvicorn storygal.app:app --host 127.0.0.1 --port 8000` and `npm --prefix frontend run dev` in separate terminals.

```sh
uv run --project backend ruff check backend/src backend/tests tools/export_prompt_kit.py tools/release_files.py tools/build_release.py
uv run --project backend python tools/export_prompt_kit.py --check
python3 tools/release_files.py --check
npm --prefix frontend run build
npm --prefix frontend run test:reader
uv run --project backend pytest backend/tests/test_text.py backend/tests/test_api.py backend/tests/test_speech.py backend/tests/test_production_bundles.py backend/tests/test_continuity.py backend/tests/test_release.py
uv run --project backend pytest backend/tests/test_review.py -k "not export"
uv run --project backend python tools/build_release.py --output .release/local-check
```

Some historical tests need the old full Chibi/Last Light packs or optional WebGAL assets. They remain available for integration checks; the two full-pack tests skip explicitly if those local packs are absent. Synthetic sound tests exercise import/export without distributing system audio. Full historical suite: install optional WebGAL with `./start.sh --with-webgal`, retain local historical samples, then run `uv run --project backend pytest backend/tests`.

## Change rules

Preserve source bytes. Anchor claims to source evidence. AI output is a candidate, never automatic approval. Version mutable records and invalidate dependent checks when input changes. Keep old editable projects readable and exports independent of the workbench.

Prompt changes belong in `backend/src/storygal/prompt_library.json`; regenerate with `tools/export_prompt_kit.py`. Generated Markdown and schemas must not drift from runtime rules. Templates need actual input/output examples and an honest capability boundary.

Image contributions should identify the exact source moment, each person's stance, identity references, prompt, provenance and licensing. Include a failed case when claiming a repair. Follow [character direction](docs/人物视觉导演标准.md). Never relabel assistant checks as creator sign-off.

Use Issues to report a specific failure, expected outcome and reproduction steps. Source excerpts and images are optional. Do not include credentials, private manuscripts, runtime data or personal reading history.

## Local packages and releases

`uv run --project backend python tools/package_source.py` packages only `tools/public-source.json`, without uploading. After reviewing and staging intended new files, maintainers run `python3 tools/release_files.py --refresh` and review the changed inventory. `uv run --project backend python tools/build_release.py` builds the prompt starter, sound-free editable Last Light project and standalone reader in temporary storage. Add `--chibi-source` with the pinned public 0.1 reader for a complete release. No image or paid model calls occur. See [release procedure](docs/RELEASING.md).

Original Last Light rebuild: `uv run --project backend python tools/build_content_pack.py samples/last-light/recipe.json --output data/rebuilt.storygal.zip` against a running local workbench. This creates a new project. Existing hash-bound assistant checks may be replayed only for unchanged recipe and image files; changing a recipe or image requires fresh inspection.
