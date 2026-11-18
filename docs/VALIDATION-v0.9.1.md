# 0.9.1: acceptance is by book, not just by ZIP

This record describes the checks on the 0.9.1 release build. The [GitHub release](https://github.com/Ethereal-Space-one/taleprism/releases/tag/v0.9.1) supplies the four readers; the [reading room](https://ethereal-space-one.github.io/taleprism/) serves the Chibi reader from that release. A matching checksum proves the file you have is the file the packager produced; it does not prove that sound survived import, or that an illustration still appears after the verse it belongs with.

## Book contracts

| Book | Positive control | Negative and continuity controls |
| --- | --- | --- |
| Chibi | 67 original text blocks; one 12-second wind WAV on block 12, UTF‑8 start 5183; search `旗旛轉動` and use the manual sound control to hear it directly. | Other 66 blocks have no soundscape. Preserve all 12 illustration descriptions; keep the two display delays 6014 → 6136 and 15974 → 16035. First-plate shore motion is inherited, not the new cue. No voiced dialogue or narration. |
| Last Light | 9 original text blocks; one 12-second rain WAV on block 2 at byte 22, searchable as `傍晚的雨`. | No car, no added voice, no soundscape on the other eight blocks. Keep all three illustrations and the existing station rain on the first. |
| The Door Left Open | Four blocks, one protected wet-road illustration, rain and one passing car on block 2. | No soundtrack elsewhere. Preserve the still boots and threshold, the existing sound bytes and the reviewed motion. Reader only. |
| The Margin | Six blocks; pencil cue on block 6; the fold at block 5 quotes block 2. | Keep the single illustration static. Do not generate speech, motion, extra echoes or an authoring backup. Reader only. |

For the editable examples, import each released-format project into a new empty store. Export with the **ordinary workbench path**. Check the resulting reader directly, with no identity or presentation patch afterwards. A restored editable gets its own local project ID; the separately distributed reader keeps the public work and illustration identities. Extra sound, missing sound, misplaced cues, new narration/dialogue, missing visual descriptions and incorrect display timing are separate failures. See the [machine-readable edition contract](../tools/edition-contract.json).

## Verified in the local candidate

- Two independent builds reproduced the same archive SHA-256 for each of the Chibi and Last Light reader/project pairs (four ZIPs).
- All six browser paths were exercised: the four delivered reading editions plus one ordinary, unmodified export from each of the two reimported projects. This tested author restore → reader export, not only the packaged public-looking reader.
- In same-origin 0.9.0 → candidate reader migration checks, both books retained the position within a plate, its within-plate offset, a bookmark and text size. The two checked source positions were 13990 in Chibi and 1521 in Last Light. A legacy Chibi record with a paragraph-start byte and a plate ID still normalized to the intended position. This does not promise that different file paths, browsers, or origins share storage.

## Observed reader-discovery check

On 2026-11-18 the two rebuilt candidate reader ZIPs were extracted and opened using `file://` in Linux Chromium. With fresh 390- and 1180-pixel viewports, **Quiet reading → Search → select the one matching passage → the paragraph’s sound button** worked in all four cases. Searching `旗旛轉動` returned one hit and the sound button identified paragraph 12; searching `傍晚的雨` returned one hit and identified paragraph 2. The audio element stayed paused after the search jump, advanced beyond 0.5 seconds after the explicit click, and made no HTTP requests. This verifies the written shortcut, not a physical-phone listening test or the full edition gate.

## Hosted edition

The Chibi reading room was verified separately at the existing `/taleprism/` address against the published 0.9.1 Chibi reader. This hosted check is distinct from building the ZIPs or promoting a GitHub release. Old downloaded readers remain unchanged.

## Reproduce

Use the locked backend and frontend dependencies, build the reader, install the project's browser QA dependencies, and substitute your own existing output directory, Chromium executable, and **new** report path:

```sh
uv run --project backend python tools/check_edition_semantics.py \
  --output "$OUT" --chromium /path/to/chromium \
  --report "$OUT/edition-acceptance.json"
```

The full gate takes four reader ZIPs and two project ZIPs; the latter produce two further cold reader exports. It checks source bytes, exact media and per-book intentions, then exercises the actual files in Chromium. A static-only diagnostic is not a browser pass, a stale receipt is not a new result, and a local result is not evidence that Pages changed. A later hosted check must compare the served files with the approved Chibi reader, not only compare version strings. The previous live archive must remain available for rollback.

Actual playhead advance and visible changed pixels in desktop Chromium do not establish physical-device Safari behavior, loudspeaker quality, independent human acceptance, or a new art sign-off. This document does not authorize a tag, release upload or deployment.
