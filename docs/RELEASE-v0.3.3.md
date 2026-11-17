# Taleprism v0.3.3 Public Preview

[中文说明](../README.md) · [English](../README.en.md) · [Read Chibi](https://ethereal-space-one.github.io/taleprism/) · [Downloads](https://github.com/Ethereal-Space-one/taleprism/releases/tag/v0.3.3)

## Changes

- Review chapter art already reached in the text without revealing future plates. Deliberate whole-chapter browsing remains a separate choice.
- Enable bounded environmental motion explicitly. Effects require exact edition/image evidence, respect reduced-motion/static fallbacks and stop when the view closes or changes.
- Bind Last Light rain to its audited normalized exported PNG, including rebuilt projects whose asset IDs differ.
- Keep authoring Prompt handoff separate from the renderer: the former is guidance for a human's external tool workflow; runtime effects are finite hand-written overlays, not image/video generation or a per-drop physical causality simulation.

## Downloads and compatibility

The six ZIPs are the curated source, prompt starter, Chibi editable project and standalone reader, and Last Light editable project and standalone reader. Verify their exact bytes with `SHA256SUMS` and `release-manifest.json`. Extract readers and serve them over HTTP, or use their loopback-only macOS launchers; import project ZIPs into the workbench. The source archive excludes dependencies, runtime data, credentials and packed examples.

Application version 0.3.3 is independent of prompt-library 0.2.1, editable-project format v2 and the reviewed Chibi 0.2.0 reconstruction recipe. Canonical text, all 27 Chibi images, public work identity and 12 legacy illustration IDs are preserved. Existing tags and release attachments remain unchanged.

## Validation boundaries

See [the validation record](VALIDATION-v0.3.3.md) for executed local checks and outstanding platform/publication checks. Linux and desktop-browser checks do not establish Safari, physical-phone/touch or macOS Finder/Gatekeeper acceptance. The Chibi fire-ship flag-color paired-shot review remains `needs_revision`; no artwork correction is applied. Final creator art review and independent external-user onboarding remain separate from assistant software/production checks.
