# 许可与内容来源

项目自有代码与文档采用根目录 MIT 许可证。文本、图像、声音、下载的引擎及依赖分别以其来源说明为准，不因进入本仓库而改换许可。

- 赤壁正文：见 `samples/sanguo-chibi/PROVENANCE.md`，保留版本、来源与转换记录。
- 赤壁人物、场景和叙事图：见相应 `samples/**/PROVENANCE.md`、`prompts.json` 与人物 README。由 Codex 内置生图制作的项目自有示例图允许随 Storygal 示例复用、修改和再分发，并应保留来源记录；AI 生成结果不承诺独占性。参考的第三方文本及史地资料不因此重新授权。
- 《末班灯》：本项目新写的虚构短篇与内置生图样例，以 MIT 提供，见 `samples/last-light/PROVENANCE.md`。无真实人物声纹克隆。
- macOS 系统合成音频：作为本地演示生成，制作记录保留音色、读音文本哈希和文件哈希；不打包系统音色模型或授予其使用权。公开分发时可选择不含音频的内容包；本地完整包含演示音频。
- WebGAL 4.6.5：可选下载组件，MPL-2.0；其正文补丁及许可随对应成品保存，原引擎不纳入本地源码发布包。
- 简繁通搜使用 [opencc-js 1.4.2](https://github.com/nk2028/opencc-js/tree/v1.4.2)：代码 MIT，随包 `opencc-data` 派生字典 Apache-2.0。仅使用 generic `t2s`，不作地区词汇转换；本地确定性匹配，无运行时字典下载或网络转换。独立阅读包的 `licenses/` 保留代码许可、Apache-2.0 全文及字典第三方说明。
- Python 与前端依赖按各自许可证分发；具体版本以 `backend/uv.lock`、`frontend/package-lock.json` 和 `tools/webgal-verify/package-lock.json` 为准。独立阅读成品附带前端运行依赖许可。

许可文本来源：[OSI MIT](https://opensource.org/license/mit)。代码许可不替代创作者对其导入文本和素材使用范围的判断。
