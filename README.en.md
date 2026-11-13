# Taleprism

**An open workflow for turning fiction into illustrated reading experiences, with character direction, scene continuity, and optional voice.**

v0.2.0 Public Preview · [中文](README.md) · [Read Chibi](https://ethereal-space-one.github.io/taleprism/) · [Downloads](https://github.com/Ethereal-Space-one/taleprism/releases/tag/v0.2.0)

![Chibi: the Red Cliffs reading showcase](examples/chibi/cover.png)

**Chibi showcases the reading experience; Last Light teaches the production workflow.** The public demo includes 12 scene illustrations, eight principal characters, nine portraits and three historical map stages. The [Last Light short-story tutorial and materials](examples/last-light/README.en.md) remain in Git.

## Two ways to use it

- **Prompt workflow:** use the [eight templates](prompts/README.md) and [complete English walkthrough](examples/last-light/README.en.md) with your chosen AI tools. No workbench installation or API key is required by the toolkit; your AI service may require an account and payment.
- **Local workbench:** import a chapter, review speakers and characters, direct illustrations, track props, inspect continuity, optionally produce voice, and export an editable project or standalone reader.

The online example is a static reading experience. It has no hosted editing backend. Image generation happens in an external tool; the webpage cannot call a Codex conversation's built-in image generator.

## Install the workbench

Requirements: Python 3.11+ (uv can manage it), [uv](https://docs.astral.sh/uv/getting-started/installation/), Node.js 22.12+ and npm. The UI is currently Chinese. macOS is the primary manually tested environment; see [validation](docs/VALIDATION-v0.2.0.md) for the exact platform checks. Native Windows startup is not supported.

```sh
git clone https://github.com/Ethereal-Space-one/taleprism.git
cd taleprism
./start.sh
```

Open `http://127.0.0.1:8000`. Initial dependency installation needs internet. Later use `./run.sh`; on macOS the Taleprism `.command` launchers also work. The service binds to localhost. Restart it after rebooting.

Download the Chibi or Last Light `project.zip` from the v0.2.0 Release. In the left sidebar choose **示例与工程 → 导入可编辑工程** (Examples and projects → Import editable project). Each import creates a new project. Chibi provides a complete chapter and ensemble example; Last Light provides a three-shot tutorial. The source checkout includes tutorial reference images; complete projects download separately.

Both projects include unchanged source text, assets, direction plans and assistant inspection evidence. Unfinished projects can be restored for repair; old checks without dependency evidence require reinspection. Public packages omit macOS system-generated demonstration audio. Final creator art review is still pending.

## Make a chapter

1. Import your TXT (one chapter or short story, up to 30,000 characters). The original stays immutable.
2. Review identities and dialogue speakers in **人物与审校**.
3. In **章节制作方案**, select a paragraph for each picture; write moment, exact evidence, framing, separate acting for each person, and forbidden early revelations.
4. Establish a scene master and every important object's state. Export prompts/tasks, attach reference images in your image tool, then upload and accept the result in **阅读器与场景**. Assign it to the shot, approve the plan, compare master/previous/current images, record checks, then apply.
5. Optionally prepare a few important dialogue lines in **对白配音**, listen and accept. Preview and export an independent reader.

For external text AI, export a complete workbench task and import `{source_sha256, plan}`. Do not turn human tutorial paragraph IDs into byte offsets yourself. Text services use your local `.env`; only explicit AI operations send text. Keep credentials local.

## Downloads

- `prompt-starter.zip`: templates, complete tutorial, source and actual reference images.
- `last-light-project.zip`: import into the workbench to continue editing.
- `chibi-project.zip`: the editable twelve-shot Chibi project with reference-bound checks.
- `chibi-reader.zip`: the complete standalone Chibi reading showcase.
- `last-light-reader.zip`: extract and serve over HTTP to read without the workbench.
- `source.zip` or GitHub Source code ZIP: application source and tutorial references; project packages download separately.

Check the unified `SHA256SUMS` and `release-manifest.json`. Previous release attachments remain available. Inside the extracted reader directory run:

```sh
python3 verify_package.py
python3 -m http.server 8080 --bind 127.0.0.1
```

Open `http://127.0.0.1:8080`, not a `file://` HTML page.

## What is verified, and what is not

Last Light demonstrates a fixed-camera scene workflow, including actual repairs for an extended bench and a missing bicycle basket. Minor brushwork and contour drift remain. Other models, arbitrary reverse shots and whole-book automation are not validated. A prompt or a software test cannot approve visual quality.

The [second-story worksheet](examples/archive-room/README.md) checks general evidence/state handling without model calls; it does not claim a second successful image generation run. External-user usability is still unverified.

Local speech uses macOS voices and ffmpeg. Existing audio travels with editable projects. The OpenAI voice adapter is prepared but has not been live-validated. No voice cloning is included. Optional WebGAL export is installed with `./start.sh --with-webgal`. [Chibi](examples/chibi/README.md) is the public showcase; its approximate historical maps explain camps and movements, and are not a general map-generation service.

The legacy `storygal` module, `STORYGAL_*` environment variables, bundle format identifiers and browser progress keys stay compatible in this release. See [compatibility](docs/COMPATIBILITY.md).

## Contribute

Report the exact failed step or visual inconsistency through [Issues](https://github.com/Ethereal-Space-one/taleprism/issues/new/choose). Never submit API keys; source excerpts and images are optional. [Contributing](CONTRIBUTING.md) · [Architecture](docs/ARCHITECTURE.md) · [Changelog](CHANGELOG.md)

Code and prompts: [MIT](LICENSE). Content and dependencies retain their own [provenance and notices](THIRD_PARTY_NOTICES.md). AI-generated images are not claimed to be exclusive. Earlier Storygal contributors remain credited.
