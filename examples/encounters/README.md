# 两种随读演绎 · Two reading editions

下载 [v0.9.0 预览版](https://github.com/Ethereal-Space-one/taleprism/releases/tag/v0.9.0) 中相应的 `-reader.zip`，完整解压，打开 `index.html`。正文不改字、不强制翻页，不需要安装或联网。

- **留门 / The Door Left Open**：在雨落铁篷、车辆驶过的那段听见短声景；门槛外湿路轻轻动，靴子保持静止。静音只关声音，系统「减少动态效果」只关动作。
- **留白处 / The Margin**：旧历书托住桌角，是一幅不动的画。原句在后段才重新出现，末段响几笔短促的铅笔声；其余时间留白。

The two stories and illustrations were created specifically for Taleprism. The rain, passing car and pencil sounds are synthesized locally by the repository’s soundscape renderer; there are no recordings, sampled voices, stock art, fonts embedded in the illustrations, or third-party story excerpts. The project’s [MIT license](../../LICENSE) applies to these original texts, artwork and procedural cues. Runtime dependencies retain their separately distributed notices. The examples are fixed authored decisions, not evidence of a live inference-provider call. Physical Safari/iOS support has not been verified.

Each subdirectory contains only the original passage, final image and adopted reader presentation. The editions ship as readers only, not as editable projects. To rebuild with an installed backend and frontend dependencies, first build the frontend and run `PYTHONPATH=backend/src python tools/build_encounter_readers.py --output <dir>`. Sound is generated from the two public recipes, not shipped as input audio.
