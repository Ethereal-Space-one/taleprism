# Taleprism

**Keep every word of the story. Let a map explain a battle or a passing car break the quiet at the moment the text calls for it.** Taleprism is a local authoring workbench and a standalone reader. A passage that needs no sound or picture stays on the page as prose.

**[Read Chibi (Red Cliffs) online](https://ethereal-space-one.github.io/taleprism/) · [Download Chibi for offline reading](https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.9.0/taleprism-v0.9.0-chibi-reader.zip) · [Download The Door Left Open and hear the rain](https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.9.0/taleprism-v0.9.0-the-door-left-open-reader.zip)** · [v0.9.0 public preview and downloads](https://github.com/Ethereal-Space-one/taleprism/releases/tag/v0.9.0) · [中文](README.md)

**Which version has the wind?** The public links above still open **0.9.0**: its Chibi shore illustration can move, but the book has no audio track. The **local 0.9.1 candidate** adds wind at one Chibi passage and rain at one Last Light passage. Neither the published ZIPs nor the current website has been replaced.

## The classical showcase: Chibi, a battle map that doesn't give away the ending

![Chibi: raising the wind at the altar and the fire attack on the river](examples/chibi/cover.png)

In chapters 49 and 50 of *Romance of the Three Kingdoms*, commanders shift allegiance and fleets change position. A map drawn with hindsight would reveal the retreat before the reader reaches the battle. Here, the three stages of the map, faction ties and chains of cause and effect unfold with the text. Read back and later outcomes disappear again. Browse the illustrations you have reached without opening the whole chapter's gallery.

Twelve illustrations follow eight principal characters. The maker's plan tracks who has seen what and which boat an object belongs on; a change of camera angle doesn't erase the previous scene. The public 0.9.0 edition uses no voices or ambient soundtrack. To see how it works, [open the editable Chibi project](https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.9.0/taleprism-v0.9.0-chibi-project.zip) alongside its [shot and continuity notes (Chinese)](examples/chibi/README.md).

**In the 0.9.1 candidate, listen for the flags.** Only paragraph 12 of 67 has a soundscape: twelve seconds of synthesized wind at 「忽聽風聲響，旗旛轉動」. For a shortcut, open the candidate reader, choose **搜索** (Search) in the reading toolbar, search for `旗旛轉動`, select the hit, then choose **听此处声景 · 风声** at the end of the paragraph. Searching or going back does not replay cues you skipped. Reading forward normally encounters the cue in place. The shore waves on the first illustration already worked in 0.9.0; the wind does not animate the other eleven illustrations.

## The modern showcase: The Door Left Open

A cobbler has lowered the shutter halfway. A pair of small yellow boots sits on the threshold. The first paragraph is silent. Reach the second and rain strikes the metal awning; a car passes the mouth of the lane, closest at six seconds. Only the wet road on the right of the illustration moves. The boots and the dry threshold stay still. When the rain stops in the story, the reader doesn't play it again as a closing theme.

[The Door Left Open](https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.9.0/taleprism-v0.9.0-the-door-left-open-reader.zip) is the short introduction to 0.9's passage-timed design. A smaller experiment, [The Margin](https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.9.0/taleprism-v0.9.0-the-margin-reader.zip), takes a different approach: a still life stays still, an earlier sentence returns in a fold, and a few pencil strokes give way to silence. Both downloads are readers, not editable backups.

The 0.9.1 candidate for the editable tutorial *Last Light* uses rain alone, not a passing car. Search for `傍晚的雨` and choose **听此处声景 · 细雨** at the second paragraph. The first illustration keeps its existing station-rain motion. See the [repair notes and book-by-book acceptance criteria](docs/RELEASE-v0.9.1.md).

## Open a book and set its pace

1. **Download a Reader ZIP → extract it fully → open `index.html` in that folder.** Keep the assets beside the HTML. Don't open the HTML in a ZIP preview. Reading needs no terminal, network, workbench or model key.
2. The cover stays silent. Choose **开始阅读** (Start reading): an adopted soundscape can play once at its passage, and a picture appears where the author placed it. Only separately reviewed motion can animate. If your browser blocks the first sound, use the prompt inside the reader; don't change browser permissions.
3. **安静阅读** (Quiet reading) leaves the cues for you to try manually. Pause automatic cues while reading, or choose **静音** (Mute) to silence the book without hiding art or folds. System reduced motion keeps illustrations still. Passage narration is click-to-play; character dialogue retains its own settings. Nothing turns the page for you.

**The same Chibi, online and off.** The web edition now uses the **0.9.0** Chibi reader from the release. Open the online link to start reading, or extract the download to read without a connection. Older ZIPs do not update themselves. The Door Left Open and The Margin remain offline downloads.

## Make an edition: choose the passage before the effect

In the Chinese-language workbench, choose **用自己的图文开始**, import a TXT, inspect an illustration you have permission to distribute and place it after the right paragraph. That is a finished edition if you want it to be. Add a licensed passage recording or compose a soundscape only where it helps. Listen before accepting it. To add rain or shore motion, mark the actual region on the image and review it instead of animating the whole frame.

**One More Thing** is an optional last reading of the work, not a “generate book” button. Ask for a suggestion about sound, imagery or presentation, or accept that none is needed. Local rules are identified as rules; asking an external model is an explicit step that confirms which text goes to which endpoint. Only adopted arrangements enter the reader. The reader itself never calls a model.

**Share a Reader; keep the Editable backup for authoring.** Backups may contain rejected material, notes or review history. For a first production exercise, follow the [three-shot Last Light tutorial](examples/last-light/README.en.md). The local workbench needs Python 3.11+, [uv](https://docs.astral.sh/uv/getting-started/installation/), Node.js 22.12+ and npm. Run `./start.sh` from the directory that contains it, then open the local address it prints. Initial setup needs a network connection. Use `./run.sh` on subsequent runs. No native Windows launcher is included.

[Quick start (Chinese)](docs/快速上手.md) · [Eight prompt templates](prompts/README.md) · [Reproducible Reading Lab](examples/reading-lab/README.md) · [Iteration history (Chinese)](docs/ITERATION-HISTORY.md) · [Validation and limits](docs/VALIDATION-v0.9.0.md) · [Contributing](CONTRIBUTING.md)

Code and prompts are [MIT-licensed](LICENSE). See the separate [content and dependency notices](THIRD_PARTY_NOTICES.md) and keep the credits included with each reader.
