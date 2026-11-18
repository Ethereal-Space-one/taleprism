# Reading Lab / 阅读实验台

Two small, original test texts for running the public author-to-reader checks. These are functional fixtures, not additional release downloads or recordings. The text, geometry and sample proposals were written for this repository and are distributed under its MIT license. No external artwork, fonts, audio, project backups or account data are needed.

- **试印条 / Proof Strip**: import `proof-strip/source.txt`, then the three source-bound proposal files. The illustration belongs after paragraph 3. Paragraph 5 can recall the exact words “先看边线” from paragraph 2. A short synthetic pencil cue belongs only to paragraph 6. The `quiet/` control keeps both paragraphs untouched.
- **集水格 / Rain Grid**: the proposed sound belongs to paragraph 2. The illustration follows that paragraph. Only the right, blue collection area should move; the beige crosshairs stay still. `edition.json` supplies sample inputs for the director, not an automatically accepted author review.

To regenerate the geometric PNGs, run `python examples/reading-lab/draw_tiles.py`. To make actual disposable readers with the built workbench, run `tools/check_creative_edition.py` and `tools/check_soundscape_browser.py` with different fresh `--output` directories. Each writes `reader.zip`. The manual and automatic reading checks are separate.
